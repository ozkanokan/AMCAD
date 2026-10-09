from copy import deepcopy
import json
import math
import pytest
from core.cavity import CavityProfile,ProfileVertex,Corner,HydraulicInterface,PhysicalDefinition
from core.cavity_surface import (SurfaceAnchor,ChannelSection,surface_patches,resolve_anchor,
    revolved_surface,normalized,interface_pose,section_frame,section_outline,channel_mesh,dot,sub)
from core.component_definition import ComponentDefinition
from core.project import Project
from core.library import ComponentLibrary
from core.port import PortDefinition
from examples.create_physical_demo import check_valve_definition


def cylinder(): return CavityProfile([ProfileVertex(0,3),ProfileVertex(10,3)])


def anchored(profile,kind='CIRCLE',t=.5,angle=0):
    a,b=profile.vertices[:2]
    return HydraulicInterface('IN','SURFACE',surface_anchor=SurfaceAnchor('LINE',a.id,b.id,t,angle),
                              direction=(1,2,3),section=ChannelSection(kind),section_rotation_deg=30,preview_length_mm=7,preview_mode="FORWARD")


def test_revolved_surface_coordinates_open_endpoints_and_fillets():
    p=cylinder(); m=revolved_surface(p,angular_steps=16)
    assert len(m.vertices)==34 and len(m.triangles)==32
    assert m.vertices[0]==pytest.approx((3,0,0))
    assert m.vertices[4]==pytest.approx((0,3,0))
    assert m.vertices[17]==pytest.approx((3,0,10))
    assert all(math.hypot(x,y)==pytest.approx(3) for x,y,z in m.vertices)
    assert all(len({m.vertices[i][2] for i in face})==2 for face in m.triangles) # no caps
    p=check_valve_definition().physical.cavity_profile
    mesh=revolved_surface(p,angular_steps=16,arc_steps=12)
    assert any(anchor.kind=='FILLET' for anchor,_ in mesh.anchors)
    assert any(anchor.kind=='CHAMFER' for anchor,_ in mesh.anchors)
    assert len(p.vertices)==6
    assert any(7.5<z<8 and 6.5<math.hypot(x,y)<7 for x,y,z in mesh.vertices)


@pytest.mark.parametrize('angle,expected',[(0,(3,0,5)),(90,(0,3,5)),(180,(-3,0,5)),(270,(0,-3,5))])
def test_anchor_angle_and_normal(angle,expected):
    p=cylinder(); i=anchored(p,angle=angle)
    xyz,normal=resolve_anchor(p,i.surface_anchor)
    assert xyz==pytest.approx(expected)
    assert normal==pytest.approx((expected[0]/3,expected[1]/3,0))


def test_fillet_chamfer_anchors_follow_evaluated_features_not_theoretical_vertices():
    p=check_valve_definition().physical.cavity_profile
    for index,kind in [(1,'FILLET'),(3,'CHAMFER')]:
        vertex=p.vertices[index]; a=SurfaceAnchor(kind,vertex.id,t=.5,angle_deg=90)
        xyz,normal=resolve_anchor(p,a)
        feature=p.features()[index]
        if kind=='FILLET':
            angle=math.radians(feature['start_deg']+feature['sweep_deg']/2)
            expected=(feature['center'][0]+feature['radius']*math.cos(angle),feature['center'][1]+feature['radius']*math.sin(angle))
        else: expected=tuple((x+y)/2 for x,y in zip(feature['entry'],feature['exit']))
        assert xyz==pytest.approx((0,expected[1],expected[0]))
        assert (xyz[2],xyz[1])!=(vertex.z,vertex.r)
        assert math.hypot(*normal)==pytest.approx(1)


def test_profile_edits_regenerate_anchor_and_insertion_invalidates_original_pair():
    p=cylinder(); i=anchored(p); anchor=deepcopy(i.surface_anchor)
    before,_=interface_pose(p,i)
    p.edit_point(p.vertices[1].id,12,4)
    after,_=interface_pose(p,i)
    assert after!=before and after==pytest.approx((3.5,0,6))
    assert i.surface_anchor==anchor
    p.add_point(6,3.5,after_id=p.vertices[0].id)
    with pytest.raises(ValueError,match='original'): resolve_anchor(p,anchor)
    assert i.surface_anchor==anchor


def test_changing_or_deleting_corner_invalidates_anchor_without_retargeting():
    p=check_valve_definition().physical.cavity_profile; v=p.vertices[1]
    a=SurfaceAnchor('FILLET',v.id)
    resolve_anchor(p,a)
    p.set_corner(v.id,Corner('CHAMFER',length_mm=.5,angle_deg=30))
    with pytest.raises(ValueError,match='original'): resolve_anchor(p,a)
    physical=PhysicalDefinition('REVOLVED_PROFILE',p,[HydraulicInterface('IN','SURFACE',surface_anchor=a)])
    physical.validate([PortDefinition('IN','IN')]) # unresolved anchors retain identity and can be saved
    assert 'INVALID anchor' in physical.warnings([PortDefinition('IN','IN')])[0]


@pytest.mark.parametrize('vector',[(1,2,3),(0,0,-10),(-4,.5,8)])
def test_normalization_and_deterministic_orthonormal_section_frame(vector):
    direction=normalized(vector)
    assert math.hypot(*direction)==pytest.approx(1)
    i=HydraulicInterface('IN',direction=vector)
    assert i.direction==pytest.approx(direction)
    for angle in (0,30,90,270):
        u,v=section_frame(direction,angle)
        assert math.hypot(*u)==pytest.approx(1) and math.hypot(*v)==pytest.approx(1)
        assert dot(u,direction)==pytest.approx(0,abs=1e-12)
        assert dot(v,direction)==pytest.approx(0,abs=1e-12)
        assert dot(u,v)==pytest.approx(0,abs=1e-12)
        assert (u,v)==section_frame(direction,angle)
    u0,v0=section_frame(direction,0); u90,v90=section_frame(direction,90)
    assert u90==pytest.approx(v0) and v90==pytest.approx(tuple(-v for v in u0))


@pytest.mark.parametrize('section',[
    ChannelSection('CIRCLE',diameter_mm=6),ChannelSection('SLOT',width_mm=4,length_mm=8),
    ChannelSection('RECTANGLE',width_mm=4,height_mm=8)])
def test_channel_sections_and_extrusion(section):
    p=cylinder(); i=anchored(p); i.section=section; i.direction=(0,0,1); i.section_rotation_deg=0
    outline=section_outline(section); mesh=channel_mesh(p,i)
    assert len(mesh.vertices)==2*len(outline)+2 and len(mesh.triangles)==4*len(outline)
    origin,direction=interface_pose(p,i)
    assert mesh.vertices[-2]==origin
    assert mesh.vertices[-1]==pytest.approx(tuple(a+7*b for a,b in zip(origin,direction)))
    for first,last in zip(mesh.vertices[:len(outline)],mesh.vertices[len(outline):]):
        assert sub(last,first)==pytest.approx((0,0,7))
    if section.type=='CIRCLE': assert all(math.hypot(*v)==pytest.approx(3) for v in outline)
    else:
        xs=[v[0] for v in outline]; ys=[v[1] for v in outline]
        assert max(xs)-min(xs)==pytest.approx(section.length_mm if section.type=='SLOT' else section.width_mm)
        assert max(ys)-min(ys)==pytest.approx(section.width_mm if section.type=='SLOT' else section.height_mm)


def test_section_rotation_changes_rectangle_orientation_without_drift():
    p=cylinder(); i=anchored(p,'RECTANGLE'); i.direction=(0,0,1); i.section=ChannelSection('RECTANGLE',width_mm=2,height_mm=6)
    i.section_rotation_deg=0; before=channel_mesh(p,i)
    i.section_rotation_deg=90; after=channel_mesh(p,i)
    assert before.vertices!=after.vertices
    assert before.vertices[-2:]==after.vertices[-2:]
    assert after.vertices==channel_mesh(p,HydraulicInterface.from_dict(json.loads(json.dumps(vars_without_objects(i))))).vertices


def vars_without_objects(interface):
    from dataclasses import asdict
    return asdict(interface)


@pytest.mark.parametrize('section',[ChannelSection('CIRCLE',diameter_mm=0),
    ChannelSection('SLOT',width_mm=5,length_mm=4),ChannelSection('RECTANGLE',height_mm=-1),ChannelSection('UNKNOWN')])
def test_invalid_sections_rejected(section):
    with pytest.raises(ValueError): section.validate()


@pytest.mark.parametrize('direction',[(0,0,0),(1,float('nan'),0),(1,2),(True,0,1)])
def test_invalid_directions_rejected(direction):
    with pytest.raises(ValueError): normalized(direction)


def test_legacy_pose_preserved_and_new_surface_library_project_json_roundtrip(tmp_path):
    p=cylinder()
    legacy=HydraulicInterface.from_dict({'hydraulic_port_id':'IN','interface_type':'AXIAL','z_mm':28,'r_mm':0,
                                        'nominal_connection_diameter_mm':4,'preferred_direction':'AXIAL_POSITIVE','id':'legacy'})
    assert interface_pose(p,legacy)==((0,0,28),(0,0,1)) and legacy.surface_anchor is None
    radial=HydraulicInterface('OUT','RADIAL',14.5,7,4,'RADIAL')
    assert interface_pose(p,radial)==((0,7,14.5),(0,1,0))
    marker=anchored(p,'SLOT',angle=32.125)
    definition=ComponentDefinition('surface','Surface Valve','CV','Valves',[PortDefinition('IN','IN')],physical=PhysicalDefinition('REVOLVED_PROFILE',p,[marker]))
    definition.validate(); original=deepcopy(definition.to_dict()); mesh=channel_mesh(p,marker)
    library=ComponentLibrary(tmp_path/'library'); library.save(definition)
    loaded=ComponentLibrary(tmp_path/'library').definitions[definition.id]
    assert loaded.to_dict()==original
    project=Project(); project.add_instance(loaded); project.add_instance(loaded,200,0); project.save(tmp_path/'p.json')
    reopened=Project.load(tmp_path/'p.json'); physical=reopened.definitions[definition.id].physical
    assert physical.cavity_profile.to_dict()==p.to_dict()
    assert channel_mesh(physical.cavity_profile,physical.hydraulic_interfaces[0]).vertices==mesh.vertices
    data=json.loads((tmp_path/'p.json').read_text())
    assert data['schema_version']==7
    assert all('physical' not in instance for instance in data['component_instances'])
    assert 'triangles' not in json.dumps(data) and 'mesh' not in json.dumps(data)
    assert len(data['component_definitions'])==1


@pytest.mark.parametrize('vector',[(1e-30,0,0),(1e308,1e308,1e308),(0,-1e-300,0)])
def test_direction_normalization_avoids_underflow_overflow(vector):
    direction=normalized(vector)
    assert all(math.isfinite(v) for v in direction)
    assert math.hypot(*direction)==pytest.approx(1)
