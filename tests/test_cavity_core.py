from copy import deepcopy
import math
import pytest
from core.cavity import CavityProfile,ProfileVertex,Corner,PhysicalDefinition,HydraulicInterface,snapped
from core.component_definition import ComponentDefinition
from core.port import PortDefinition
from core.project import Project
from core.library import ComponentLibrary


def stepped_profile():
    return CavityProfile([ProfileVertex(0,5),ProfileVertex(10,5),ProfileVertex(10,8),ProfileVertex(25,8)])


def test_adjacent_retracing_rejected_but_straight_extension_valid():
    with pytest.raises(ValueError,match='retraces'):
        CavityProfile([ProfileVertex(0,5),ProfileVertex(10,5),ProfileVertex(6,5)]).validate()
    CavityProfile([ProfileVertex(0,5),ProfileVertex(10,5),ProfileVertex(16,5)]).validate()


def check_definition():
    p=stepped_profile(); p.set_corner(p.vertices[1].id,Corner('FILLET',radius_mm=.5))
    p.set_corner(p.vertices[2].id,Corner('CHAMFER',length_mm=.4,angle_deg=45))
    return ComponentDefinition('test-check','Illustrative Check Valve','CV','Valves',[
        PortDefinition('IN','IN',side='LEFT'),PortDefinition('OUT','OUT',side='RIGHT')],
        internal_relationships=[{'from_port_id':'IN','to_port_id':'OUT','relationship':'CHECK_VALVE'}],
        physical=PhysicalDefinition('REVOLVED_PROFILE',p,[
            HydraulicInterface('IN','AXIAL',25,0,4,'AXIAL_POSITIVE'),
            HydraulicInterface('OUT','RADIAL',14.5,8,4,'RADIAL')]))


def test_definition_shared_profile_roundtrip_library_and_instances(tmp_path):
    d=check_definition().validate(); original=d.to_dict(); ids=[v.id for v in d.physical.cavity_profile.vertices]
    lib=ComponentLibrary(tmp_path/'library'); lib.save(d)
    reopened=ComponentLibrary(tmp_path/'library').definitions[d.id]
    assert reopened.to_dict()==original
    p=Project('Physical'); a=p.add_instance(reopened); b=p.add_instance(reopened,300,0)
    assert a.definition_id==b.definition_id==d.id and len(p.definitions)==1
    assert not any('physical' in i for i in p.to_dict()['component_instances'])
    p.save(tmp_path/'physical.json'); loaded=Project.load(tmp_path/'physical.json')
    assert loaded.to_dict()==p.to_dict()
    assert [v.id for v in loaded.definitions[d.id].physical.cavity_profile.vertices]==ids
    assert [i.interface_type for i in loaded.definitions[d.id].physical.hydraulic_interfaces]==['AXIAL','RADIAL']


def test_exact_fillet_chamfer_geometry_and_sharp():
    p=stepped_profile(); v=p.vertices[1]
    p.set_corner(v.id,Corner('FILLET',radius_mm=1))
    f=p.features()[1]
    assert f['entry']==pytest.approx((9,5)); assert f['exit']==pytest.approx((10,6))
    assert f['center']==pytest.approx((9,6)); assert f['sweep_deg']==pytest.approx(90)
    assert len(p.vertices)==4 and v.corner.radius_mm==1
    p.set_corner(v.id,Corner('SHARP')); assert v.corner.type=='SHARP' and (v.z,v.r)==(10,5)
    p.set_corner(v.id,Corner('CHAMFER',length_mm=1,angle_deg=30))
    f=p.features()[1]
    assert f['entry']==pytest.approx((9,5))
    assert f['exit']==pytest.approx((10,5+math.tan(math.radians(30))))
    assert len(p.vertices)==4


@pytest.mark.parametrize('corner',[Corner('FILLET',radius_mm=0),Corner('FILLET',radius_mm=-1),
    Corner('FILLET',radius_mm=20),Corner('CHAMFER',length_mm=0,angle_deg=45),
    Corner('CHAMFER',length_mm=1,angle_deg=0),Corner('CHAMFER',length_mm=1,angle_deg=90),
    Corner('CHAMFER',length_mm=20,angle_deg=45)])
def test_impossible_corner_is_transactional(corner):
    p=stepped_profile(); before=p.to_dict()
    with pytest.raises(ValueError): p.set_corner(p.vertices[1].id,corner)
    assert p.to_dict()==before


def test_endpoint_overlap_and_point_edit_rejection():
    p=stepped_profile()
    with pytest.raises(ValueError,match='adjacent'): p.set_corner(p.vertices[0].id,Corner('FILLET',radius_mm=.5))
    p.set_corner(p.vertices[1].id,Corner('FILLET',radius_mm=2))
    before=p.to_dict()
    with pytest.raises(ValueError,match='overlap'): p.set_corner(p.vertices[2].id,Corner('FILLET',radius_mm=2))
    assert p.to_dict()==before
    with pytest.raises(ValueError): p.edit_point(p.vertices[0].id,9.9,5)
    assert p.to_dict()==before
    with pytest.raises(ValueError,match='negative'): p.edit_point(p.vertices[0].id,0,-1)
    assert p.to_dict()==before


def test_numeric_edits_insertion_ids_snap():
    p=stepped_profile(); v=p.vertices[0]; vertex_id=v.id
    p.edit_point(vertex_id,.123456,5.654321)
    assert p.vertex(vertex_id).z==.123456 and p.vertex(vertex_id).r==5.654321
    inserted=p.add_point(5,5.5,after_id=vertex_id)
    assert p.vertices[1].id==inserted.id
    p.delete_point(inserted.id); assert p.vertices[0].id==vertex_id
    assert snapped(.26,.74,0)==(.26,.74)
    assert snapped(.26,.74,.1)==(.3,.7)
    assert snapped(.26,.74,.5)==(.5,.5)
    assert snapped(.26,.74,1)==(0,1)
    assert snapped(1,-1,0)==(1,0)


@pytest.mark.parametrize('vertices',[[],[ProfileVertex(0,1)], [ProfileVertex(0,-1),ProfileVertex(1,1)],
    [ProfileVertex(0,1),ProfileVertex(0,1)], [ProfileVertex(0,1),ProfileVertex(4,5),ProfileVertex(0,5),ProfileVertex(4,1)]])
def test_invalid_profiles_have_reasons(vertices):
    p=CavityProfile(vertices)
    assert p.validation_errors()
    with pytest.raises(ValueError): p.validate()


def test_interface_consistency_and_missing_mapping_warning():
    d=check_definition(); physical=d.physical
    physical.hydraulic_interfaces.pop()
    assert physical.warnings(d.ports)==['Required port OUT has no physical interface']
    d.validate()  # Missing mapping is a warning, not destruction of a valid sketch.
    physical.hydraulic_interfaces.append(HydraulicInterface('MISSING'))
    with pytest.raises(ValueError,match='unknown'): d.validate()
    physical.hydraulic_interfaces[-1]=HydraulicInterface('IN')
    with pytest.raises(ValueError,match='Duplicate physical'): d.validate()


def test_legacy_definition_and_v12_project_preserve_geometry():
    d=check_definition().to_dict(); del d['physical']
    loaded=ComponentDefinition.from_dict(d)
    assert loaded.physical.cavity_type=='NONE' and loaded.physical.cavity_profile is None
    p=Project(); p.add_instance(loaded); data=p.to_dict(); data['schema_version']=3
    for definition in data['component_definitions']: definition.pop('physical')
    assert Project.from_dict(data).definitions[loaded.id].physical.cavity_type=='NONE'
