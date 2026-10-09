"""V1.4b geometric annotation and real Qt interaction regressions."""
from copy import deepcopy
import math
import pytest
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtTest import QTest
from core.cavity import CavityProfile,ProfileVertex,Corner,PhysicalDefinition
from core.cavity_surface import surface_patches,resolve_anchor,normalized,channel_mesh,dot,cross
from core.port import PortDefinition
from core.project import Project
from core.component_definition import ComponentDefinition
from ui.cavity_editor import CavityEditor,InterfaceDialog
from ui.cavity_surface_view import CavitySurfaceView
from ui.cavity_sketch_view import corner_dimensions


def profile():
    p=CavityProfile([ProfileVertex(*v) for v in [(0,0),(0,4),(10,4),(10,0)]])
    p.set_corner(p.vertices[1].id,Corner('FILLET',radius_mm=.5))
    return p


@pytest.mark.parametrize('radius',[.05,.5,1])
@pytest.mark.parametrize('zoom',[12,40,80])
def test_radius_leader_exact_center_arc_arrow_and_label(qapp,radius,zoom):
    p=profile(); p.set_corner(p.vertices[1].id,Corner('FILLET',radius_mm=radius))
    e=CavityEditor([PortDefinition('IN','IN')],PhysicalDefinition('REVOLVED_PROFILE',p));e.show();qapp.processEvents()
    try:
        original=e.profile.to_dict();e.view.resetTransform();e.view.scale(zoom,zoom);e.view.centerOn(0,-4)
        e.view.viewport().repaint();qapp.processEvents()
        d=corner_dimensions(e.profile)[0]; f=e.profile.features()[1]
        assert d['center']==f['center'] and math.dist(d['target'],d['center'])==pytest.approx(radius)
        layout=next(v for v in e.view.dimension_layout if v['vertex_id']==p.vertices[1].id)
        center=layout['center']; tip=layout['target']; end=layout['leader_end']; unit=layout['arrow_direction']
        expected=e.view.viewportTransform().map(QPointF(d['target'][0],-d['target'][1]))
        assert tip==expected
        radial=tip-center; extension=end-tip
        assert radial.x()*extension.y()-radial.y()*extension.x()==pytest.approx(0,abs=1e-8)
        assert radial.x()*extension.x()+radial.y()*extension.y()>0
        assert unit.x()*radial.x()+unit.y()*radial.y()>0 # arrow base outside, tip on arc
        assert end==layout['rect'].center() and e.profile.to_dict()==original
    finally:e.reject()


def test_header_far_edge_click_collapses_without_hiding_channels(qapp):
    p=profile();e=CavityEditor([PortDefinition('IN','IN')],PhysicalDefinition('REVOLVED_PROFILE',p));e.show();qapp.processEvents()
    try:
        before=e.surface_views['ISO'].surface
        for panel,other in ((e.vertices_panel,e.interface_group),(e.interface_group,e.vertices_panel)):
            assert panel.header.width()==panel.width()
            QTest.mouseClick(panel.header,Qt.LeftButton,pos=QPoint(panel.header.width()-8,panel.header.height()//2));qapp.processEvents()
            assert not panel.contents.isVisible() and other.contents.isVisible()
            assert e.surface_views['ISO'].surface is before
            QTest.mouseClick(panel.header,Qt.LeftButton,pos=QPoint(panel.header.width()-8,panel.header.height()//2));qapp.processEvents()
            assert panel.contents.isVisible()
    finally:e.reject()


@pytest.mark.parametrize('direction',[(0,-2,0),(0,0,-3),(-2,-3,-4),(1,0,0)])
def test_arbitrary_axis_direction_sign_roundtrip_and_centered_preview(qapp,tmp_path,direction):
    p=profile();ports=[PortDefinition('IN','IN')];a=next(patch.anchor for patch in surface_patches(p) if patch.anchor.kind=='LINE' and patch.evaluate(.5)[0][1]==4)
    a.angle_deg=90; d=InterfaceDialog(ports,[],profile=p,anchor=a)
    try:
        xyz,n=resolve_anchor(p,a)
        assert tuple(w.value() for w in d.vector)==pytest.approx(n,abs=.0005)
        for field,value in zip(d.vector,direction):field.setValue(value)
        d.submit();m=d.result_marker
        assert m is not None and m.direction==pytest.approx(normalized(direction))
        expected=deepcopy(m);mesh=channel_mesh(p,m)
        assert mesh.vertices[-2]==pytest.approx(tuple(x-v for x,v in zip(xyz,m.direction)))
        assert mesh.vertices[-1]==pytest.approx(tuple(x+v for x,v in zip(xyz,m.direction)))
        definition=ComponentDefinition(id='axis-test',name='Axis test',prefix='AX',category='Test',ports=ports,physical=PhysicalDefinition('REVOLVED_PROFILE',p,[m]))
        project=Project();project.add_instance(definition);project.save(tmp_path/'axis.json')
        loaded=Project.load(tmp_path/'axis.json').definitions[definition.id].physical
        assert loaded.hydraulic_interfaces==[expected]
        assert channel_mesh(loaded.cavity_profile,loaded.hydraulic_interfaces[0]).vertices==mesh.vertices
        edit=InterfaceDialog(ports,[m],m,profile=p);edit.submit()
        assert edit.result_marker.direction==m.direction;edit.reject()
    finally:d.reject()


def test_zero_axis_still_rejected(qapp):
    p=profile();d=InterfaceDialog([PortDefinition('IN','IN')],[],profile=p,anchor=surface_patches(p)[0].anchor)
    try:
        for field in d.vector:field.setValue(0)
        d.submit();assert d.result_marker is None and 'nonzero' in d.feedback.text()
    finally:d.reject()


def test_trackball_can_reach_opposite_end_and_stays_orthonormal(qapp):
    v=CavitySurfaceView('ISO');v.resize(600,600);v.show();qapp.processEvents()
    try:
        center=deepcopy(v.center);original=v.basis()[2];start=QPointF(300,300)
        for _ in range(4):v.orbit(start,QPointF(300,540))
        assert dot(original,v.basis()[2])<-.8 # No elevation limit: opposite end reachable.
        for i in range(400):
            v.orbit(QPointF(250,280),QPointF(252+math.sin(i),281+math.cos(i)))
        right,up,depth=v.basis()
        for axis in (right,up,depth):assert math.hypot(*axis)==pytest.approx(1,abs=1e-6)
        assert abs(dot(right,up))<1e-6 and cross(right,up)==pytest.approx(depth,abs=1e-6)
        assert v.center==center
        orientation=deepcopy(v.orientation);pan=QPointF(v.pan)
        QTest.mousePress(v,Qt.RightButton,pos=QPoint(20,40));QTest.mouseMove(v,QPoint(55,70));QTest.mouseRelease(v,Qt.RightButton,pos=QPoint(55,70))
        assert v.pan!=pan and v.orientation==orientation
        QTest.mousePress(v,Qt.LeftButton,pos=QPoint(300,300));QTest.mouseMove(v,QPoint(350,330));QTest.mouseRelease(v,Qt.LeftButton,pos=QPoint(350,330))
        assert v.orientation!=orientation
    finally:v.close()
