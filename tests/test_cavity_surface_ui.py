from copy import deepcopy
import math
import pytest
from PySide6.QtCore import Qt,QPoint,QPointF,QTimer
from PySide6.QtGui import QColor,QPalette,QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog,QSplitter
from core.cavity import HydraulicInterface,PhysicalDefinition,Corner
from core.cavity_surface import SurfaceAnchor,ChannelSection,resolve_anchor,interface_pose,channel_mesh
from core.project import Project
from examples.create_physical_demo import check_valve_definition
from ui.cavity_editor import CavityEditor,InterfaceDialog


@pytest.fixture
def editor(qapp):
    d=check_valve_definition(); physical=deepcopy(d.physical); physical.hydraulic_interfaces=[]
    e=CavityEditor(d.ports,physical); e.show(); qapp.processEvents()
    yield e
    e.reject(); e.close(); qapp.processEvents()


def surface_pixel(view):
    # Find a pickable point away from the overlay/orientation labels.
    for y in range(45,view.height()-25,12):
        for x in range(30,view.width()-20,12):
            point=QPointF(x,y)
            if view.pick_surface(point) is not None: return point.toPoint()
    raise AssertionError('No surface could be picked')


def test_four_resizable_views_use_same_surface_and_update_from_profile(qapp,editor):
    assert set(editor.surface_views)=={'XZ','XY','ISO'}
    assert isinstance(editor.four_views,QSplitter)
    assert all(view.surface is not None and view.surface.vertices for view in editor.surface_views.values())
    assert len({id(view.surface) for view in editor.surface_views.values()})==1
    before=list(editor.surface_views['ISO'].surface.vertices)
    vertex=editor.profile.vertices[1]; corner=deepcopy(vertex.corner)
    editor.points.item(1,1).setText('8.125')
    qapp.processEvents()
    assert vertex.z==8.125 and vertex.corner==corner
    assert editor.surface_views['XZ'].surface.vertices!=before
    assert all(view.surface is editor.surface_views['ISO'].surface for view in editor.surface_views.values())
    sizes=editor.four_views.sizes(); editor.four_views.setSizes([sizes[0]+50,sizes[1]-50]); qapp.processEvents()
    assert editor.four_views.sizes()!=sizes
    assert editor.profile.vertices[1].id==vertex.id


def test_iso_surface_pick_create_general_slot_port_select_all_views_save_reopen(qapp,editor,tmp_path):
    iso=editor.surface_views['ISO']; point=surface_pixel(iso)
    anchor=iso.pick_surface(QPointF(point))
    assert anchor is not None
    xyz,normal=resolve_anchor(editor.profile,anchor)
    def accept():
        dialog=editor.findChildren(InterfaceDialog)[-1]
        assert dialog.kind.currentText()=='SURFACE'
        assert dialog.anchor is not None and dialog.anchor.vertex_id==anchor.vertex_id
        assert tuple(w.value() for w in dialog.vector)==pytest.approx(normal,abs=1e-10)
        dialog.port.setCurrentText('OUT')
        for field,value in zip(dialog.vector,(1,2,3)): field.setValue(value)
        dialog.section_type.setCurrentText('SLOT'); dialog.width.setValue(3); dialog.length.setValue(7)
        dialog.rotation.setValue(32.5); dialog.preview_length.setValue(9.25); dialog.submit()
    QTimer.singleShot(0,accept)
    editor.begin_surface_port(); QTest.mouseClick(iso,Qt.LeftButton,pos=point); qapp.processEvents()
    assert len(editor.interfaces)==1 and not editor.surface_place_mode
    marker=editor.interfaces[0]
    assert marker.hydraulic_port_id=='OUT' and marker.section.type=='SLOT'
    assert marker.direction==pytest.approx((1/math.sqrt(14),2/math.sqrt(14),3/math.sqrt(14)))
    assert marker.section_rotation_deg==32.5 and marker.preview_length_mm==9.25
    assert all(view.selected_port==marker.id for view in editor.surface_views.values())
    assert editor.view.marker_items[marker.id].isSelected()
    assert editor.markers.currentRow()==0
    assert interface_pose(editor.profile,marker)[0]==pytest.approx(xyz)
    mesh=channel_mesh(editor.profile,marker)
    expected=deepcopy(editor.profile.to_dict()); expected_marker=deepcopy(marker)
    editor.submit(); assert editor.result()==QDialog.Accepted
    d=check_valve_definition(); d.physical=editor.result_physical
    project=Project(); project.add_instance(d); project.save(tmp_path/'surface.json')
    loaded=Project.load(tmp_path/'surface.json').definitions[d.id]
    reopen=CavityEditor(loaded.ports,loaded.physical); reopen.show(); qapp.processEvents()
    try:
        assert reopen.profile.to_dict()==expected
        assert reopen.interfaces==[expected_marker]
        assert reopen.surface_views['ISO'].channels[marker.id].vertices==mesh.vertices
        reopen.select_surface_port(marker.id); reopen.grab().save('/tmp/amcad-v14-four-views.png')
    finally: reopen.reject()


def test_selected_port_and_channels_follow_anchor_after_theoretical_edit(qapp,editor):
    a,b=editor.profile.vertices[:2]
    marker=HydraulicInterface('IN','SURFACE',surface_anchor=SurfaceAnchor('LINE',a.id,b.id,t=.5,angle_deg=90),
                              direction=(0,1,.25),section=ChannelSection('RECTANGLE',width_mm=3,height_mm=5))
    editor.interfaces.append(marker); editor.view.rebuild(); editor.refresh_markers(); editor.profile_changed()
    before=interface_pose(editor.profile,marker)[0]; parameters=deepcopy(marker)
    editor.select_surface_port(marker.id)
    assert editor.selected_port_id==marker.id
    editor.points.item(1,1).setText('8.5'); qapp.processEvents()
    after=interface_pose(editor.profile,marker)[0]
    assert after!=before and marker==parameters
    for view in editor.surface_views.values(): assert view.channels[marker.id].vertices[-2]==after
    assert editor.view.marker_items[marker.id].pos()==QPointF(after[2],-after[1])
    xy=editor.surface_views['XY']; pixel=xy.project(after)[0]
    QTest.mouseClick(xy,Qt.LeftButton,pos=pixel.toPoint())
    assert all(view.selected_port==marker.id for view in editor.surface_views.values())
    assert editor.view.marker_items[marker.id].isSelected()


def test_invalid_anchor_flagged_hidden_but_can_be_explicitly_reattached(qapp,editor):
    vertex=editor.profile.vertices[1]
    marker=HydraulicInterface('IN','SURFACE',surface_anchor=SurfaceAnchor('FILLET',vertex.id),direction=(1,0,0))
    original_anchor=deepcopy(marker.surface_anchor)
    editor.interfaces.append(marker); editor.view.rebuild(); editor.profile_changed()
    editor.points.item(1,3).setText('0'); qapp.processEvents()
    assert marker.surface_anchor==original_anchor
    assert 'INVALID anchor' in editor.warnings.text()
    assert editor.markers.item(0,1).text()=='INVALID anchor'
    assert all(marker.id not in view.channels for view in editor.surface_views.values())
    assert not editor.view.marker_items[marker.id].isVisible()
    editor.markers.setCurrentCell(0,0); qapp.processEvents()
    assert editor.selected_port_id==marker.id and editor.markers.currentRow()==0
    def reattach():
        dialog=editor.findChildren(InterfaceDialog)[-1]
        assert 'INVALID' in dialog.feature.currentText()
        dialog.feature.setCurrentIndex(1); dialog.parameter.setValue(.25); dialog.azimuth.setValue(90); dialog.submit()
    QTimer.singleShot(0,reattach); editor.edit_marker(); qapp.processEvents()
    assert editor.interfaces[0].id==marker.id
    assert editor.interfaces[0].surface_anchor.kind=='LINE'
    assert 'INVALID anchor' not in editor.warnings.text()
    assert all(marker.id in view.channels for view in editor.surface_views.values())


def test_orbit_pan_zoom_and_escape_surface_placement_do_not_modify_profile(qapp,editor):
    view=editor.surface_views['ISO']; before=editor.profile.to_dict(); yaw=view.yaw
    start=QPoint(20,40); end=QPoint(60,70)
    QTest.mousePress(view,Qt.LeftButton,pos=start); QTest.mouseMove(view,end,delay=20); QTest.mouseRelease(view,Qt.LeftButton,pos=end)
    assert view.yaw!=yaw
    pan=QPointF(view.pan)
    QTest.mousePress(view,Qt.MiddleButton,pos=start); QTest.mouseMove(view,end,delay=20); QTest.mouseRelease(view,Qt.MiddleButton,pos=end)
    assert view.pan!=pan
    zoom=view.zoom
    event=QWheelEvent(QPointF(60,60),QPointF(view.mapToGlobal(QPoint(60,60))),QPoint(),QPoint(0,120),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
    qapp.sendEvent(view,event)
    assert view.zoom>zoom and editor.profile.to_dict()==before
    editor.begin_surface_port(); assert all(v.place_mode for v in editor.surface_views.values())
    QTest.keyClick(view,Qt.Key_Escape)
    assert editor.isVisible() and not editor.surface_place_mode
    assert all(not v.place_mode for v in editor.surface_views.values())
    assert editor.profile.to_dict()==before


def test_port_dialog_section_validation_and_duplicate_schematic_identity(qapp,editor):
    a,b=editor.profile.vertices[:2]; anchor=SurfaceAnchor('LINE',a.id,b.id)
    dialog=InterfaceDialog(editor.ports,editor.interfaces,parent=editor,profile=editor.profile,anchor=anchor)
    try:
        for field in dialog.vector: field.setValue(0)
        dialog.submit(); assert dialog.result_marker is None and 'nonzero' in dialog.feedback.text()
        dialog.vector[0].setValue(1)
        dialog.section_type.setCurrentText('SLOT'); dialog.width.setValue(8); dialog.length.setValue(2)
        dialog.submit(); assert dialog.result_marker is None and 'length' in dialog.feedback.text()
        dialog.length.setValue(9); dialog.submit(); assert dialog.result()==QDialog.Accepted
        duplicate=InterfaceDialog(editor.ports,[dialog.result_marker],parent=editor,profile=editor.profile,anchor=anchor)
        assert duplicate.port.count()==1 and duplicate.port.currentText()!=dialog.result_marker.hydraulic_port_id
        duplicate.reject()
    finally: dialog.reject()


def test_dark_theme_point_table_and_numeric_inputs_have_contrast(qapp):
    original=qapp.palette(); dark=QPalette(original)
    dark.setColor(QPalette.Base,QColor('#20262d')); dark.setColor(QPalette.Text,QColor('#e5edf5'))
    dark.setColor(QPalette.Window,QColor('#252c34')); dark.setColor(QPalette.WindowText,QColor('#e5edf5'))
    qapp.setPalette(dark)
    d=check_valve_definition(); e=CavityEditor(d.ports,d.physical); e.show(); qapp.processEvents()
    try:
        assert e.points.item(0,1).foreground().color().lightness()>180
        dialog=InterfaceDialog(d.ports,[],parent=e,profile=e.profile)
        assert dialog.vector[0].palette().color(QPalette.Text).lightness()>180
        e.grab().save('/tmp/amcad-v14-dark.png'); dialog.reject()
    finally: e.reject(); qapp.setPalette(original)


def test_port_dialog_preserves_precise_anchor_direction_and_independent_circle_diameter(qapp,editor):
    a,b=editor.profile.vertices[:2]
    marker=HydraulicInterface('IN','SURFACE',nominal_connection_diameter_mm=4,
        surface_anchor=SurfaceAnchor('LINE',a.id,b.id,t=.5123456789012345,angle_deg=123.123456789012345),
        direction=(1,2,3),section=ChannelSection('CIRCLE',diameter_mm=6.123456789012345),
        section_rotation_deg=15.123456789012345,preview_length_mm=9.123456789012345)
    dialog=InterfaceDialog(editor.ports,[marker],marker,parent=editor,profile=editor.profile)
    try:
        assert dialog.circle_diameter.value()==pytest.approx(marker.section.diameter_mm)
        assert dialog.diameter.value()==4
        dialog.submit()
        # Cached legacy z/r may update once to the resolved anchor, but the
        # authoritative anchor, frame and section must keep their exact data.
        updated=dialog.result_marker
        assert updated.surface_anchor==marker.surface_anchor
        assert updated.direction==marker.direction and updated.section==marker.section
        assert updated.section_rotation_deg==marker.section_rotation_deg
        assert updated.preview_length_mm==marker.preview_length_mm
        assert updated.nominal_connection_diameter_mm==4
        second=InterfaceDialog(editor.ports,[updated],updated,parent=editor,profile=editor.profile)
        second.circle_diameter.setValue(7.5); second.submit()
        assert second.result_marker.direction==marker.direction
        assert second.result_marker.surface_anchor==marker.surface_anchor
        assert second.result_marker.section.diameter_mm==7.5
        assert second.result_marker.nominal_connection_diameter_mm==4
        second.reject()
    finally: dialog.reject()


def test_new_surface_demo_and_legacy_examples_launch_with_shared_definition(qapp,tmp_path):
    import json
    from pathlib import Path
    from core.graph import export_graph
    from ui.main_window import MainWindow
    root=Path(__file__).resolve().parents[1]
    path=root/'examples/parallel_check_valves_3d.amcad.json'
    project=Project.load(path)
    valves=[i for i in project.instances.values() if i.name in ('CV1','CV2')]
    assert len(valves)==2 and valves[0].definition_id==valves[1].definition_id
    physical=project.definitions[valves[0].definition_id].physical
    assert all(i.surface_anchor is not None for i in physical.hydraulic_interfaces)
    assert {i.section.type for i in physical.hydraulic_interfaces}=={'CIRCLE','SLOT'}
    assert export_graph(project)==json.loads((root/'examples/parallel_check_valves_3d.graph.json').read_text())
    window=MainWindow(tmp_path/'library'); window.load_path(path); window.show(); qapp.processEvents()
    preview=CavityEditor(project.definitions[valves[0].definition_id].ports,physical)
    preview.show(); qapp.processEvents()
    assert len(preview.surface_views['ISO'].channels)==2
    preview.grab().save('/tmp/amcad-v14-demo.png'); preview.reject(); window.close()
    for name in ('c1_r','parallel_check_valves'):
        p=Project.load(root/'examples'/f'{name}.amcad.json')
        p.validate()
        assert all(p.is_complete(i.id) for i in p.instances.values())
