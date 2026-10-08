"""V1.3a engineering table and real Qt interaction regressions."""
from copy import deepcopy
import math
import pytest
from PySide6.QtCore import Qt, QPointF, QTimer, QLocale
from PySide6.QtGui import QValidator
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QLineEdit, QLabel, QPushButton
from core.cavity import CavityProfile, PhysicalDefinition, Corner
from core.component_definition import ComponentDefinition
from core.library import ComponentLibrary
from core.port import PortDefinition
from core.project import Project
from examples.create_physical_demo import check_valve_definition
from ui.cavity_editor import CavityEditor, InterfaceDialog
from ui.cavity_sketch_view import corner_dimensions, profile_path


@pytest.fixture
def editor(qapp):
    definition=check_valve_definition()
    dialog=CavityEditor(definition.ports,definition.physical)
    dialog.show(); qapp.processEvents()
    yield dialog
    dialog.reject(); dialog.close(); qapp.processEvents()


def click(view,z,y):
    QTest.mouseClick(view.viewport(),Qt.LeftButton,pos=view.mapFromScene(QPointF(z,-y)))


def drag(qapp,editor,vertex,z,y,release=True):
    start=editor.view.mapFromScene(QPointF(vertex.z,-vertex.r))
    end=editor.view.mapFromScene(QPointF(z,-y))
    QTest.mousePress(editor.view.viewport(),Qt.LeftButton,pos=start)
    QTest.mouseMove(editor.view.viewport(),end,delay=20)
    qapp.processEvents()
    if release:
        QTest.mouseRelease(editor.view.viewport(),Qt.LeftButton,pos=end)
        qapp.processEvents()
    return end


def edit_cell(qapp,editor,row,column,text):
    table=editor.points
    table.setCurrentCell(row,column)
    table.editItem(table.item(row,column))
    qapp.processEvents()
    field=table.findChild(QLineEdit)
    assert field is not None
    QTest.keyClick(field,Qt.Key_A,Qt.ControlModifier)
    QTest.keyClicks(field,text)
    QTest.keyClick(field,Qt.Key_Return)
    qapp.processEvents()


def test_zy_table_terminology_and_removed_controls(editor):
    assert [editor.points.horizontalHeaderItem(i).text() for i in range(6)]==[
        '#','Z (mm)','Y (mm)','R (mm)','Chamfer (mm)','Angle (°)']
    assert 'Y = 0' in editor.view.AXIS_LABEL and 'Y ↑' in editor.view.DATUM_LABEL
    assert all('R=0' not in label.text() and 'R ↑' not in label.text() for label in editor.findChildren(QLabel))
    names={b.text() for b in editor.findChildren(QPushButton)}
    assert not names & {'Sharp','Fillet','Chamfer','Apply Corner'}
    assert len(editor.profile.vertices)==editor.points.rowCount()
    assert editor.mode.currentText()=='Edit mode'
    for row,v in enumerate(editor.profile.vertices):
        assert editor.points.item(row,0).text()==str(row+1)
        assert editor.points.item(row,0).data(Qt.UserRole)==v.id
        assert float(editor.points.item(row,1).text())==v.z
        assert float(editor.points.item(row,2).text())==v.r


def test_table_edit_selection_sync_precision_and_period_locale(qapp,editor):
    row=1; vertex=editor.profile.vertices[row]; vertex_id=vertex.id
    editor.points.setCurrentCell(row,1); qapp.processEvents()
    assert editor.view.point_items[vertex_id].isSelected()
    edit_cell(qapp,editor,row,1,'8.123456789012345')
    assert vertex.z==8.123456789012345
    assert float(editor.points.item(row,1).text())==vertex.z
    assert vertex.id==vertex_id and vertex.corner.radius_mm==.5
    editor.view.select_vertex(editor.profile.vertices[3].id)
    assert editor.points.currentRow()==3
    assert editor.selected_id==editor.profile.vertices[3].id
    assert editor.points.item(row,5).text()==''
    assert not editor.points.item(row,5).flags() & Qt.ItemIsEditable


def test_draw_and_edit_modes_preview_duplicate_hit_and_metadata(qapp,editor):
    original={v.id:deepcopy(v.corner) for v in editor.profile.vertices}
    count=len(editor.profile.vertices)
    click(editor.view,30,4); qapp.processEvents()
    assert len(editor.profile.vertices)==count  # Existing profile starts in Edit.
    editor.set_mode(True)
    editor.view.fit_profile()
    position=editor.view.mapFromScene(QPointF(30,-4))
    QTest.mouseMove(editor.view.viewport(),position); qapp.processEvents()
    assert not editor.view.preview_item.path().isEmpty()
    click(editor.view,30,4); qapp.processEvents()
    assert len(editor.profile.vertices)==count+1
    assert (editor.profile.vertices[-1].z,editor.profile.vertices[-1].r)==(30,4)
    v=editor.profile.vertices[1]
    click(editor.view,v.z,v.r); qapp.processEvents()
    assert len(editor.profile.vertices)==count+1
    assert editor.selected_id==v.id
    assert all(editor.profile.vertex(i).corner==corner for i,corner in original.items())
    editor.set_mode(False)
    assert editor.view.preview_item.path().isEmpty()
    assert all(editor.profile.vertex(i).corner==corner for i,corner in original.items())


def test_empty_profile_defaults_draw_and_escape_retains_committed_points(qapp):
    editor=CavityEditor([PortDefinition('IN','IN')]); editor.show(); qapp.processEvents()
    try:
        assert editor.mode.currentText()=='Draw mode'
        click(editor.view,2.25,4.25); click(editor.view,10,4)
        ids=[v.id for v in editor.profile.vertices]
        assert len(ids)==2
        QTest.keyClick(editor.view,Qt.Key_Escape); qapp.processEvents()
        assert editor.isVisible() and editor.mode.currentText()=='Edit mode'
        assert [v.id for v in editor.profile.vertices]==ids
        click(editor.view,15,8)
        assert len(editor.profile.vertices)==2
        QTest.keyClick(editor,Qt.Key_Escape)
        assert editor.isVisible()
    finally: editor.reject()


def test_table_corner_exclusion_default_angle_exact_geometry_and_dimensions(qapp,editor):
    vertex=editor.profile.vertices[1]; coordinates=(vertex.id,vertex.z,vertex.r)
    edit_cell(qapp,editor,1,3,'1.0')
    assert vertex.corner==Corner('FILLET',radius_mm=1)
    assert editor.points.item(1,4).text()=='0' and editor.points.item(1,5).text()==''
    assert (vertex.id,vertex.z,vertex.r)==coordinates
    assert any(profile_path(editor.profile).elementAt(i).isCurveTo() for i in range(profile_path(editor.profile).elementCount()))
    dimension=next(d for d in editor.view.dimensions if d['vertex_id']==vertex.id)
    assert dimension['text']=='R1.0'
    feature=editor.profile.features()[1]
    assert math.dist(dimension['target'],feature['center'])==pytest.approx(1)
    assert dimension['target']!=(vertex.z,vertex.r)
    edit_cell(qapp,editor,1,4,'0.5')
    assert vertex.corner==Corner('CHAMFER',length_mm=.5,angle_deg=45)
    assert editor.points.item(1,3).text()=='0'
    edit_cell(qapp,editor,1,5,'30')
    assert vertex.corner.angle_deg==30 and vertex.corner.radius_mm is None
    feature=editor.profile.features()[1]
    # Incoming is +Z; outgoing is -Y. A 30-degree cut has unequal setbacks.
    assert feature['entry']==pytest.approx((7.5,7))
    assert feature['exit']==pytest.approx((8,7-.5*math.tan(math.radians(30))))
    dimension=next(d for d in editor.view.dimensions if d['vertex_id']==vertex.id)
    assert dimension['text']=='0.5 × 30°'
    assert dimension['target']==pytest.approx(tuple((a+b)/2 for a,b in zip(feature['entry'],feature['exit'])))
    edit_cell(qapp,editor,1,4,'0')
    assert vertex.corner==Corner() and editor.points.item(1,5).text()==''
    assert not any(d['vertex_id']==vertex.id for d in editor.view.dimensions)
    assert (vertex.id,vertex.z,vertex.r)==coordinates


def test_treated_theoretical_handle_drag_regenerates_without_feature_changes(qapp,editor):
    vertex=editor.profile.vertices[1]; corner=deepcopy(vertex.corner); vertex_id=vertex.id
    original_feature=deepcopy(editor.profile.features()[1])
    editor.points.setCurrentCell(1,1); qapp.processEvents()
    assert not editor.view.construction_item.path().isEmpty()
    assert editor.view.point_items[vertex.id].pos()==QPointF(vertex.z,-vertex.r)
    drag(qapp,editor,vertex,8.5,7.5)
    assert (vertex.z,vertex.r)==(8.5,7.5)
    assert vertex.id==vertex_id and vertex.corner==corner
    assert editor.profile.features()[1]!=original_feature
    assert editor.points.currentRow()==1 and editor.selected_id==vertex_id
    assert float(editor.points.item(1,1).text())==8.5
    assert float(editor.points.item(1,2).text())==7.5
    assert editor.validity.text()=='VALID'
    editor.view.scene().clearSelection(); editor.view.hovered_id=None; editor.view.refresh_construction()
    assert editor.view.construction_item.path().isEmpty()


def test_escape_cancels_drag_and_restores_theoretical_geometry(qapp,editor):
    vertex=editor.profile.vertices[1]; before=editor.profile.to_dict()
    end=drag(qapp,editor,vertex,8.5,7.5,release=False)
    assert editor.profile.to_dict()!=before
    QTest.keyClick(editor.view,Qt.Key_Escape)
    QTest.mouseRelease(editor.view.viewport(),Qt.LeftButton,pos=end); qapp.processEvents()
    assert editor.profile.to_dict()==before and editor.isVisible()
    assert editor.view.dragging_id is None
    QTest.keyClick(editor.view,Qt.Key_Escape)
    assert editor.selected_id is None and editor.isVisible()


def test_invalid_table_corner_or_move_restores_feature_and_coordinate(qapp,editor):
    before=editor.profile.to_dict()
    edit_cell(qapp,editor,1,3,'1000')
    assert editor.profile.to_dict()==before
    assert 'rejected' in editor.feedback.text() and 'too large' in editor.feedback.text()
    assert float(editor.points.item(1,3).text())==.5
    edit_cell(qapp,editor,0,1,'7.9')  # Fillet no longer fits incoming segment.
    assert editor.profile.to_dict()==before and 'too large' in editor.feedback.text()
    edit_cell(qapp,editor,1,2,'-1')
    assert editor.profile.to_dict()==before and 'negative' in editor.feedback.text()
    edit_cell(qapp,editor,0,3,'1')
    assert editor.profile.to_dict()==before and 'adjacent' in editor.feedback.text()
    assert editor.validity.text()=='VALID'  # Last valid state was restored.


def test_table_append_insert_delete_preserve_feature_ids_and_report_conflicts(qapp,editor):
    original={v.id:deepcopy(v.corner) for v in editor.profile.vertices}
    editor.set_mode(True)
    click(editor.view,30,3); qapp.processEvents()
    appended=editor.profile.vertices[-1]
    editor.view.select_vertex(editor.profile.vertices[3].id)
    editor.insert_point(); click(editor.view,20,4); qapp.processEvents()
    inserted=editor.profile.vertices[4]
    assert (inserted.z,inserted.r)==(20,4)
    assert len(editor.profile.vertices)==8
    assert all(editor.profile.vertex(i).corner==c for i,c in original.items())
    editor.delete_point()
    editor.view.select_vertex(appended.id); editor.insert_point(); editor.delete_point()
    assert editor.view.insert_after is None
    assert [v.id for v in editor.profile.vertices]==list(original)
    editor.view.select_vertex(editor.profile.vertices[1].id); editor.insert_point()
    before=editor.profile.to_dict()
    editor.snap.setCurrentIndex(0)
    click(editor.view,8,6.6); qapp.processEvents()
    assert editor.profile.to_dict()==before and 'not added' in editor.feedback.text()
    assert all(editor.profile.vertex(i).corner==c for i,c in original.items())


def test_place_marker_then_drag_table_edit_save_reopen(qapp,tmp_path):
    definition=check_valve_definition(); physical=deepcopy(definition.physical)
    physical.hydraulic_interfaces=[]
    editor=CavityEditor(definition.ports,physical); editor.show(); qapp.processEvents()
    try:
        for port,kind,z,y in [('IN','AXIAL',28,0),('OUT','RADIAL',14.5,5)]:
            def accept_marker(port=port,kind=kind,z=z,y=y):
                dialog=editor.findChildren(InterfaceDialog)[-1]
                dialog.port.setCurrentText(port); dialog.kind.setCurrentText(kind)
                dialog.z.setValue(z); dialog.r.setValue(y); dialog.submit()
            QTimer.singleShot(0,accept_marker)
            editor.begin_marker(); click(editor.view,z,y); qapp.processEvents()
            assert not editor.view.marker_mode and editor.mode.currentText()=='Edit mode'
        markers=deepcopy(editor.interfaces)
        vertex=editor.profile.vertices[1]; vertex_id=vertex.id
        drag(qapp,editor,vertex,8.5,7.5)
        assert (vertex.z,vertex.r)==(8.5,7.5)
        edit_cell(qapp,editor,1,1,'8.625123456789')
        assert vertex.z==8.625123456789 and vertex.id==vertex_id
        assert editor.interfaces==markers
        click(editor.view,14.5,5); qapp.processEvents()
        assert editor.markers.currentRow()==1 and editor.interfaces==markers
        editor.set_mode(True); editor.set_mode(False)
        QTest.keyClick(editor.view,Qt.Key_Escape)
        assert editor.isVisible()
        editor.submit()
        assert editor.result()==QDialog.Accepted
        definition.physical=editor.result_physical
        library=ComponentLibrary(tmp_path/'library'); library.save(definition)
        project=Project(); project.add_instance(definition); project.add_instance(definition,300,0)
        project.save(tmp_path/'demo.json')
        loaded=Project.load(tmp_path/'demo.json').definitions[definition.id]
        assert loaded.to_dict()==ComponentLibrary(tmp_path/'library').definitions[definition.id].to_dict()
        reopen=CavityEditor(loaded.ports,loaded.physical); reopen.show(); qapp.processEvents()
        try:
            assert reopen.profile.to_dict()==editor.profile.to_dict()
            assert corner_dimensions(reopen.profile)==editor.view.dimensions
            assert reopen.interfaces==markers
            assert reopen.view.point_items[vertex_id].pos()==QPointF(vertex.z,-vertex.r)
            assert float(reopen.points.item(1,1).text())==8.625123456789
        finally: reopen.reject()
    finally: editor.reject()


@pytest.mark.parametrize('draw',[False,True])
def test_escape_marker_placement_restores_prior_mode_and_child_escape_normal(qapp,editor,draw):
    editor.interfaces.clear(); editor.refresh_markers(); editor.view.rebuild()
    editor.set_mode(draw)
    before=editor.profile.to_dict()
    editor.begin_marker()
    assert editor.view.marker_mode
    QTest.keyClick(editor.view,Qt.Key_Escape); qapp.processEvents()
    assert not editor.view.marker_mode and editor.view.add_mode==draw
    assert editor.isVisible() and editor.profile.to_dict()==before
    dialog=InterfaceDialog(editor.ports,editor.interfaces,parent=editor)
    dialog.show(); qapp.processEvents()
    QTest.keyClick(dialog,Qt.Key_Escape)
    assert dialog.result()==QDialog.Rejected and not dialog.isVisible()
    assert editor.isVisible()


def test_interface_scene_selection_double_click_edit_does_not_move_vertices(qapp,editor):
    before=editor.profile.to_dict()
    marker=editor.interfaces[1]
    click(editor.view,marker.z_mm,marker.r_mm)
    assert editor.markers.currentRow()==1 and editor.selected_id is None
    def accept_edit():
        dialog=editor.findChildren(InterfaceDialog)[-1]
        dialog.z.setValue(15.125); dialog.submit()
    QTimer.singleShot(0,accept_edit)
    QTest.mouseDClick(editor.view.viewport(),Qt.LeftButton,pos=editor.view.mapFromScene(QPointF(marker.z_mm,-marker.r_mm)))
    assert editor.interfaces[1].z_mm==15.125 and editor.interfaces[1].id==marker.id
    assert editor.profile.to_dict()==before
    assert not editor.view.marker_mode


def test_c_numeric_locale_under_german_default(qapp):
    original=QLocale()
    QLocale.setDefault(QLocale(QLocale.German,QLocale.Germany))
    definition=check_valve_definition()
    editor=CavityEditor(definition.ports,definition.physical); editor.show(); qapp.processEvents()
    dialog=InterfaceDialog(definition.ports,[],z=8.5,r=6.75)
    try:
        assert editor.locale().language()==QLocale.C
        edit_cell(qapp,editor,1,1,'8.125')
        assert editor.profile.vertices[1].z==8.125
        editor.points.setCurrentCell(1,1); editor.points.editItem(editor.points.item(1,1)); qapp.processEvents()
        field=editor.points.findChild(QLineEdit)
        assert field.validator().locale().decimalPoint()=='.'
        assert field.validator().validate('8,500',5)[0]==QValidator.Invalid
        QTest.keyClick(field,Qt.Key_Escape)
        assert editor.isVisible()
        assert '.' in dialog.z.text() and ',' not in dialog.z.text()
        assert dialog.r.locale().decimalPoint()=='.'
        assert all(',' not in dimension['text'] for dimension in editor.view.dimensions)
    finally:
        dialog.reject(); editor.reject(); QLocale.setDefault(original)


def test_dimension_layout_readable_at_different_zoom_and_pan(qapp,editor):
    before=editor.profile.to_dict()
    expected=deepcopy(editor.view.dimensions)
    for scale in (12,25,50):
        editor.view.resetTransform(); editor.view.scale(scale,scale); editor.view.centerOn(14 if scale<50 else 8,-5)
        editor.grab(); qapp.processEvents()
        assert editor.view.dimensions==expected
        layout=editor.view.dimension_layout
        assert len(layout)==(2 if scale<50 else 1)  # Four-view panes show only on-screen leaders.
        assert all(item['rect'].height()<40 for item in layout)
        if len(layout)>1: assert not layout[0]['rect'].intersects(layout[1]['rect'])
    assert editor.profile.to_dict()==before
    editor.preview.setChecked(True)
    editor.view.select_vertex(editor.profile.vertices[1].id)
    editor.grab().save('/tmp/amcad-cavity-v13a.png')


def test_v13a_acceptance_workflow_with_two_features_and_interfaces(qapp,tmp_path):
    definition=check_valve_definition()
    physical=deepcopy(definition.physical); physical.hydraulic_interfaces=[]
    editor=CavityEditor(definition.ports,physical); editor.show(); qapp.processEvents()
    try:
        original_ids=[v.id for v in editor.profile.vertices]
        original_theoretical=(editor.profile.vertices[1].z,editor.profile.vertices[1].r)
        editor.set_mode(True)
        click(editor.view,30,3); click(editor.view,30,1); qapp.processEvents()
        assert len(editor.profile.vertices)==8
        editor.set_mode(False)
        edit_cell(qapp,editor,0,1,'.125')
        edit_cell(qapp,editor,1,3,'1.0')
        edit_cell(qapp,editor,3,4,'.5')
        edit_cell(qapp,editor,3,5,'30')
        assert (editor.profile.vertices[1].z,editor.profile.vertices[1].r)==original_theoretical
        assert {d['text'] for d in editor.view.dimensions}=={'R1.0','0.5 × 30°'}
        corner_by_id={v.id:deepcopy(v.corner) for v in editor.profile.vertices}
        editor.view.select_vertex(original_ids[4]); editor.insert_point()
        click(editor.view,24,3); qapp.processEvents()
        assert all(editor.profile.vertex(i).corner==c for i,c in corner_by_id.items())
        editor.set_mode(False)
        for port,kind,z,y in [('IN','AXIAL',28,0),('OUT','RADIAL',14.5,5)]:
            def accept_marker(port=port,kind=kind,z=z,y=y):
                dialog=editor.findChildren(InterfaceDialog)[-1]
                dialog.port.setCurrentText(port); dialog.kind.setCurrentText(kind)
                dialog.z.setValue(z); dialog.r.setValue(y); dialog.submit()
            QTimer.singleShot(0,accept_marker)
            editor.begin_marker(); click(editor.view,z,y)
        vertex=editor.profile.vertex(original_ids[1])
        drag(qapp,editor,vertex,8.5,7.5)
        assert vertex.corner==Corner('FILLET',radius_mm=1) and (vertex.z,vertex.r)==(8.5,7.5)
        QTest.keyClick(editor.view,Qt.Key_Escape)
        assert editor.isVisible()
        expected=editor.profile.to_dict(); expected_dimensions=deepcopy(editor.view.dimensions)
        editor.submit(); assert editor.result()==QDialog.Accepted
        definition.physical=editor.result_physical
        project=Project(); project.add_instance(definition); project.save(tmp_path/'acceptance.json')
        loaded=Project.load(tmp_path/'acceptance.json').definitions[definition.id]
        reopen=CavityEditor(loaded.ports,loaded.physical); reopen.show(); qapp.processEvents()
        try:
            assert reopen.profile.to_dict()==expected
            assert reopen.view.dimensions==expected_dimensions
            assert [v.id for v in reopen.profile.vertices if v.id in original_ids]==original_ids
            assert {i.hydraulic_port_id for i in reopen.interfaces}=={'IN','OUT'}
            assert reopen.validity.text()=='VALID'
        finally: reopen.reject()
    finally: editor.reject()


def test_unchanged_marker_edit_preserves_original_floating_point_precision(qapp):
    definition=check_valve_definition(); marker=definition.physical.hydraulic_interfaces[1]
    marker.z_mm=14.123456789012345; marker.r_mm=5.123456789012345
    marker.nominal_connection_diameter_mm=4.123456789012345
    dialog=InterfaceDialog(definition.ports,definition.physical.hydraulic_interfaces,marker)
    dialog.submit()
    assert dialog.result_marker==marker
    dialog.reject()
