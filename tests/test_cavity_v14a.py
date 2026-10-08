"""Closed cavity boundaries, directional ports, and actual editor regressions."""
from copy import deepcopy
import json
import math
import pytest
from PySide6.QtCore import Qt, QLocale, QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDoubleSpinBox
from core.cavity import CavityProfile,ProfileVertex,Corner,HydraulicInterface,PhysicalDefinition
from core.cavity_surface import (SurfaceAnchor,ChannelSection,surface_patches,resolve_anchor,
    outward_direction,channel_mesh,legacy_surface_anchor,dot)
from core.port import PortDefinition
from examples.create_physical_demo import check_valve_definition
from ui.cavity_editor import CavityEditor,InterfaceDialog


def rectangle(reverse=False):
    points=[(0,0),(0,4),(10,4),(10,0)]
    if reverse: points.reverse()
    return CavityProfile([ProfileVertex(*p) for p in points])


@pytest.mark.parametrize('index',[0,-1])
@pytest.mark.parametrize('corner',[Corner('FILLET',radius_mm=.5),Corner('CHAMFER',length_mm=.5,angle_deg=30)])
def test_endpoint_treatments_use_virtual_closure_without_changing_vertices(index,corner):
    p=rectangle(); before=[(v.id,v.z,v.r) for v in p.vertices]
    p.set_corner(p.vertices[index].id,corner); p.validate(revolved=True)
    points=p.display_points()
    assert points[0][1]==pytest.approx(0) and points[-1][1]==pytest.approx(0)
    assert all(y>=-1e-12 for _,y in points)
    assert before==[(v.id,v.z,v.r) for v in p.vertices]
    assert all(not (s.anchor.vertex_id==p.vertices[-1].id and s.anchor.next_vertex_id==p.vertices[0].id) for s in surface_patches(p))
    restored=CavityProfile.from_dict(json.loads(json.dumps(p.to_dict())))
    assert restored.to_dict()==p.to_dict() and restored.display_points()==points
    restored.edit_point(restored.vertices[index].id,restored.vertices[index].z+.125,0)
    assert restored.vertices[index].corner==corner
    restored.validate(revolved=True)


def test_treatments_on_both_endpoints_and_closure_conflict():
    p=rectangle()
    for i in (0,-1): p.set_corner(p.vertices[i].id,Corner('FILLET',radius_mm=1))
    p.validate(revolved=True)
    p= CavityProfile([ProfileVertex(*v) for v in [(0,0),(0,10),(2,10),(2,0)]])
    p.vertices[0].corner=Corner('FILLET',radius_mm=1.1)
    p.vertices[-1].corner=Corner('FILLET',radius_mm=1.1)
    assert 'virtual closure' in p.validation_errors(revolved=True)[0]
    assert p.vertices[0].corner.radius_mm==1.1


@pytest.mark.parametrize('points',[
    [(0,0),(10,0)], [(0,0),(5,0),(10,0)],
    [(0,0),(3,4),(5,0),(7,4),(10,0)],
    [(0,1),(5,4),(10,0)], [(0,0),(5,4),(10,1)],
    [(0,0),(8,4),(2,4),(10,0)]])
def test_invalid_finished_boundaries(points):
    p=CavityProfile([ProfileVertex(*v) for v in points]); assert p.validation_errors(revolved=True)


def test_nonmonotonic_z_preserves_traversal_and_valid_area():
    p=CavityProfile([ProfileVertex(*v) for v in [(0,0),(0,6),(8,6),(8,3),(5,3),(5,2),(10,2),(10,0)]])
    p.validate(revolved=True); before=[v.id for v in p.vertices]
    p.add_point(6,3,after_id=p.vertices[3].id)
    assert [v.id for v in p.vertices if v.id in before]==before
    p.validate(revolved=True)


@pytest.mark.parametrize('reverse',[False,True])
@pytest.mark.parametrize('phi',[0,90,123.456])
def test_outward_normals_independent_of_traversal(reverse,phi):
    p=rectangle(reverse)
    patch=next(s for s in surface_patches(p) if s.evaluate(.5)[0][1]==4 and s.evaluate(.5)[1][1]==0)
    a=deepcopy(patch.anchor); a.angle_deg=phi
    xyz,n=resolve_anchor(p,a); expected=(math.cos(math.radians(phi)),math.sin(math.radians(phi)),0)
    assert n==pytest.approx(expected)
    assert outward_direction(p,a,tuple(-3*v for v in n))==pytest.approx(n)
    assert dot(outward_direction(p,a,n),n)>1-1e-12
    for d in ((0,0,0),(0,0,1),tuple(n[i]*1e-8+(1 if i==2 else 0) for i in range(3))):
        with pytest.raises(ValueError): outward_direction(p,a,d)


@pytest.mark.parametrize('kind',['CIRCLE','SLOT','RECTANGLE'])
def test_new_centered_preview_and_legacy_forward_extent(kind):
    p=rectangle(); patch=surface_patches(p)[1]; a=patch.anchor
    xyz,n=resolve_anchor(p,a)
    marker=HydraulicInterface('IN','SURFACE',surface_anchor=a,direction=n,section=ChannelSection(kind))
    mesh=channel_mesh(p,marker)
    assert marker.preview_length_mm==2 and marker.preview_mode=='CENTERED'
    assert mesh.vertices[-2]==pytest.approx(tuple(x-d for x,d in zip(xyz,n)))
    assert mesh.vertices[-1]==pytest.approx(tuple(x+d for x,d in zip(xyz,n)))
    from dataclasses import asdict
    data=asdict(marker); data.pop('preview_mode'); data['preview_length_mm']=12.3456789012345
    old=HydraulicInterface.from_dict(data)
    assert old.preview_mode=='FORWARD' and old.preview_length_mm==12.3456789012345
    assert channel_mesh(p,old).vertices[-2]==pytest.approx(xyz)
    data.pop('preview_length_mm'); assert HydraulicInterface.from_dict(data).preview_length_mm==10


def test_legacy_anchor_migration_requires_exact_known_position():
    p=rectangle(); m=HydraulicInterface('IN','RADIAL',5,4)
    anchor=legacy_surface_anchor(p,m)
    assert anchor is not None and anchor.angle_deg==90
    assert resolve_anchor(p,anchor)[0]==pytest.approx((0,4,5))
    for z,y in ((5,4.01),(10,0),(50,4)):
        assert legacy_surface_anchor(p,HydraulicInterface('IN','RADIAL',z,y)) is None
    assert m.surface_anchor is None


def test_window_layout_collapsibles_and_axis_endpoint_controls(qapp):
    ports=[PortDefinition('IN','IN')]; e=CavityEditor(ports); e.show(); qapp.processEvents()
    try:
        assert len(e.profile.vertices)==2 and [v.r for v in e.profile.vertices]==[0,0]
        assert not e.save_button.isEnabled() and e.mode.currentIndex()==0
        top,bottom=e.four_views.widget(0),e.four_views.widget(1)
        assert top.widget(0) is e.view and top.widget(1) is e.surface_views['XY']
        assert bottom.widget(0) is e.surface_views['XZ'] and bottom.widget(1) is e.surface_views['ISO']
        assert e.windowFlags() & Qt.WindowMaximizeButtonHint
        assert e.view.horizontalScrollBarPolicy()==Qt.ScrollBarAlwaysOff
        assert e.view.verticalScrollBarPolicy()==Qt.ScrollBarAlwaysOff
        ids=[v.id for v in e.profile.vertices]
        assert not e.points.item(0,2).flags() & Qt.ItemIsEditable
        e.points.item(0,2).setText('1'); assert e.profile.vertices[0].r==0
        e.view.point_items[ids[0]].setPos(1,-3); assert e.profile.vertices[0].r==0 and e.profile.vertices[0].z==1
        for z,y in ((1,4),(9,4)):
            QTest.mouseClick(e.view.viewport(),Qt.LeftButton,pos=e.view.mapFromScene(QPointF(z,-y))); qapp.processEvents()
        assert [v.id for v in e.profile.vertices if v.id in ids]==ids
        assert e.validity.text()=='VALID' and e.save_button.isEnabled()
        surfaces=[v.surface for v in e.surface_views.values()]
        for panel,other in ((e.vertices_panel,e.interface_group),(e.interface_group,e.vertices_panel)):
            QTest.mouseClick(panel.header,Qt.LeftButton); qapp.processEvents()
            assert not panel.contents.isVisible() and other.contents.isVisible()
            assert [v.surface for v in e.surface_views.values()]==surfaces
            QTest.mouseClick(panel.header,Qt.LeftButton)
        e.resize(1700,1000); qapp.processEvents(); assert e.width()==1700
        e.showMaximized(); qapp.processEvents(); assert e.isMaximized()
        e.showNormal(); qapp.processEvents(); assert e.isVisible()
    finally: e.reject()


def test_legacy_invalid_geometry_is_not_modified_on_open(qapp):
    d=check_valve_definition(); original=deepcopy(d.to_dict()['physical']); e=CavityEditor(d.ports,d.physical)
    try:
        assert e.profile.to_dict()==original['cavity_profile']
        assert e.validity.text().startswith('INVALID') and not e.save_button.isEnabled()
        assert all(v.surface is None for v in e.surface_views.values())
        ids=[v.id for v in e.profile.vertices]; corners=[deepcopy(v.corner) for v in e.profile.vertices]
        e.correct_endpoints()
        assert e.profile.vertices[0].r==e.profile.vertices[-1].r==0
        assert [v.id for v in e.profile.vertices]==ids and [v.corner for v in e.profile.vertices]==corners
        assert d.to_dict()['physical']==original
    finally: e.reject()


def test_grouped_port_dialog_precision_normals_and_inward_correction(qapp):
    p=rectangle(); a=surface_patches(p)[1].anchor; a.angle_deg=90
    oldlocale=QLocale(); QLocale.setDefault(QLocale(QLocale.German))
    d=InterfaceDialog([PortDefinition('IN','IN')],[],profile=p,anchor=a)
    try:
        assert not any(hasattr(d,name) for name in ('kind','direction','use_r'))
        assert 'Z' in d.feature.currentText() and 'Y' in d.feature.currentText()
        assert tuple(w.value() for w in d.vector)==pytest.approx(resolve_anchor(p,a)[1],abs=.0005)
        for w in d.findChildren(QDoubleSpinBox):
            assert w.decimals()==3 and w.locale().decimalPoint()=='.'
            assert len(w.text().split('.')[-1])==3
        for w,x in zip(d.vector,(0,-2,0)): w.setValue(x)
        d.submit(); assert d.result_marker.direction==pytest.approx((0,1,0))
        assert d.result_marker.preview_length_mm==2 and d.result_marker.preview_mode=='CENTERED'
    finally: d.reject(); QLocale.setDefault(oldlocale)


def test_endpoint_corner_table_and_feature_highlight(qapp):
    p=rectangle(); e=CavityEditor([PortDefinition('IN','IN')],PhysicalDefinition('REVOLVED_PROFILE',p))
    e.show(); qapp.processEvents()
    try:
        ids=[v.id for v in e.profile.vertices]
        e.points.item(0,3).setText('.5'); e.points.item(3,4).setText('.5'); e.points.item(3,5).setText('30')
        assert e.profile.vertices[0].corner.type=='FILLET' and e.profile.vertices[-1].corner.angle_deg==30
        assert [v.id for v in e.profile.vertices]==ids
        assert {d['text'] for d in e.view.dimensions}=={'R0.5','0.5 × 30°'}
        a=next(s.anchor for s in surface_patches(e.profile) if s.anchor.kind=='FILLET')
        d=InterfaceDialog(e.ports,[],parent=e,profile=e.profile,anchor=a)
        assert 'R_fillet 0.500' in d.feature.currentText()
        assert e.view.feature_item is not None and not e.view.feature_item.path().isEmpty()
        d.reject(); assert e.view.feature_item.path().isEmpty()
        e.view.point_items[ids[0]].setPos(.5,-2)
        assert e.profile.vertices[0].r==0 and e.profile.vertices[0].corner.radius_mm==.5
        assert e.validity.text()=='VALID'
    finally: e.reject()


def test_legacy_dialog_exact_migration_and_unresolved_location_preservation(qapp):
    p=rectangle(); ports=[PortDefinition('IN','IN')]
    m=HydraulicInterface.from_dict({'hydraulic_port_id':'IN','interface_type':'RADIAL','z_mm':5,'r_mm':4,'preview_length_mm':8.123456789})
    original=deepcopy(m); d=InterfaceDialog(ports,[m],m,profile=p)
    d.submit()
    assert d.result_marker.surface_anchor is not None and d.result_marker.interface_type=='SURFACE'
    assert d.result_marker.id==m.id and d.result_marker.z_mm==5 and d.result_marker.r_mm==4
    assert d.result_marker.preview_length_mm==8.123456789 and d.result_marker.preview_mode=='FORWARD'
    assert m==original; d.reject()
    m.z_mm=50.123456789; m.r_mm=4.123456789; d=InterfaceDialog(ports,[m],m,profile=p)
    d.submit()
    assert d.result_marker.surface_anchor is None and d.result_marker.interface_type=='RADIAL'
    assert d.result_marker.z_mm==m.z_mm and d.result_marker.r_mm==m.r_mm
    d.reject()


def test_refined_example_editor_save_reopen_preserves_shared_data(qapp,tmp_path):
    from core.project import Project
    from examples.create_refined_surface_demo import create_refined_surface_demo
    from ui.cavity_sketch_view import corner_dimensions
    project=create_refined_surface_demo(); d=project.definitions['illustrative-check-valve']
    expected=deepcopy(d.to_dict()); e=CavityEditor(d.ports,d.physical); e.show(); qapp.processEvents()
    try:
        assert e.validity.text()=='VALID' and all(v.surface for v in e.surface_views.values())
        assert len(e.surface_views['ISO'].channels)==2
        e.grab().save('/tmp/amcad-v14a-editor.png')
        dimensions=deepcopy(e.view.dimensions); e.submit()
        d.physical=e.result_physical
        project.save(tmp_path/'refined.json'); loaded=Project.load(tmp_path/'refined.json')
        assert loaded.definitions[d.id].to_dict()==expected
        reopen=CavityEditor(d.ports,loaded.definitions[d.id].physical)
        try:
            assert corner_dimensions(reopen.profile)==dimensions
            assert reopen.interfaces==e.interfaces
        finally: reopen.reject()
    finally: e.reject()
