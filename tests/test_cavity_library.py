"""Independent cavity ownership, revisions, assignments and portable JSON snapshots."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import pytest
from core.cavity import CavityProfile,ProfileVertex,HydraulicInterface,Corner
from core.cavity_definition import CavityDefinition,legacy_cavity
from core.cavity_library import CavityLibrary
from core.cavity_surface import SurfaceAnchor,ChannelSection,channel_mesh,resolve_anchor
from core.component_definition import ComponentDefinition
from core.port import PortDefinition,new_id
from core.project import Project
from core.history import ProjectHistory
from core.graph import export_graph
from examples.create_physical_demo import check_valve_definition


def cavity(name='Reusable cavity',count=1):
    profile=CavityProfile([ProfileVertex(*p) for p in [(0,0),(0,4),(10,4),(10,0)]])
    profile.set_corner(profile.vertices[1].id,Corner('FILLET',radius_mm=.5))
    markers=[]
    for i in range(count):
        uid=new_id()
        markers.append(HydraulicInterface(uid,'SURFACE',id=uid,surface_anchor=SurfaceAnchor('LINE',profile.vertices[1].id,profile.vertices[2].id,t=.3+i*.1,angle_deg=90),direction=(0,-1,0),section=ChannelSection('SLOT',width_mm=2,length_mm=5),section_rotation_deg=12.123456789))
    return CavityDefinition(name,profile,markers).validate()


def component(count=1):
    return ComponentDefinition('component','Component','C','Test',[PortDefinition(f'P{i}',f'Port {i}') for i in range(count)])


def mapping(c):return {f'P{i}':m.id for i,m in enumerate(c.interfaces)}


def test_independent_persistence_restart_and_derived_count(tmp_path):
    library=CavityLibrary(tmp_path/'cavities');c=cavity(count=2);saved=library.save(c)
    assert saved.revision==1 and saved.port_count==2
    assert CavityLibrary(tmp_path/'cavities').definitions[c.id].to_dict()==c.to_dict()
    data=c.to_dict();data['port_count']=10
    with pytest.raises(ValueError,match='count'):CavityDefinition.from_dict(data)
    assert c.interfaces[0].hydraulic_port_id==c.interfaces[0].id


def test_default_directory_configuration(tmp_path,monkeypatch):
    monkeypatch.setenv('AMCAD_CAVITY_LIBRARY',str(tmp_path/'chosen'))
    assert CavityLibrary().directory==tmp_path/'chosen'


def test_duplicate_remaps_corner_anchors_and_does_not_share_mutable_data(tmp_path):
    c=cavity();uid=new_id();c.interfaces.append(HydraulicInterface(uid,'SURFACE',id=uid,surface_anchor=SurfaceAnchor('FILLET',c.profile.vertices[1].id),direction=(1,0,0)))
    copy=c.duplicate();copy.validate()
    assert copy.id!=c.id and copy.revision==1 and copy.profile.id!=c.profile.id
    assert {m.id for m in copy.interfaces}.isdisjoint(m.id for m in c.interfaces)
    assert {v.id for v in copy.profile.vertices}.isdisjoint(v.id for v in c.profile.vertices)
    for before,after in zip(c.interfaces,copy.interfaces):
        assert resolve_anchor(c.profile,before.surface_anchor)==resolve_anchor(copy.profile,after.surface_anchor)
        assert channel_mesh(c.profile,before).vertices==channel_mesh(copy.profile,after).vertices
    copy.profile.vertices[2].z=11;copy.interfaces[0].section.width_mm=3
    assert c.profile.vertices[2].z==10 and c.interfaces[0].section.width_mm==2


def test_instance_assignments_independent_shared_and_removed(tmp_path):
    p=Project();definition=component();a=p.add_instance(definition,name='R');b=p.add_instance(definition,name='RET')
    ca,cb=cavity('A'),cavity('B');p.assign_cavity(a.id,ca,mapping(ca));p.assign_cavity(b.id,cb,mapping(cb))
    assert a.cavity_ref!=b.cavity_ref and definition.physical.cavity_type=='NONE'
    p.assign_cavity(b.id,ca,mapping(ca));assert len(p.cavity_usage(ca.id))==2
    p.remove_cavity_assignment(a.id);assert b.cavity_ref==ca.id and a.port_mapping=={}
    p.validate()


@pytest.mark.parametrize('bad_mapping',[{}, {'P0':'missing'}, {'OTHER':'missing'}, {'P0':None}])
def test_incomplete_or_unknown_mapping_rejected(bad_mapping):
    p=Project();i=p.add_instance(component());c=cavity();before=p.to_dict()
    with pytest.raises(ValueError):p.assign_cavity(i.id,c,bad_mapping)
    assert p.to_dict()==before


def test_duplicate_interface_mapping_and_count_incompatibility():
    p=Project();i=p.add_instance(component(2));c=cavity(count=2)
    with pytest.raises(ValueError,match='one-to-one'):p.assign_cavity(i.id,c,{'P0':c.interfaces[0].id,'P1':c.interfaces[0].id})
    with pytest.raises(ValueError):p.assign_cavity(i.id,cavity(),{'P0':'x','P1':'y'})


@pytest.mark.parametrize('invalid',['profile','anchor','direction','section','identity','duplicate_id'])
def test_invalid_cavities_cannot_be_assigned_or_saved(tmp_path,invalid):
    c=cavity()
    if invalid=='profile':c.profile.vertices[0].r=1
    elif invalid=='anchor':c.interfaces[0].surface_anchor.vertex_id='missing'
    elif invalid=='direction':c.interfaces[0].direction=(0,0,0)
    elif invalid=='section':c.interfaces[0].section.width_mm=-1
    elif invalid=='identity':c.interfaces[0].hydraulic_port_id='SCHEMATIC_NAME'
    else:c.interfaces.append(deepcopy(c.interfaces[0]))
    p=Project();i=p.add_instance(component())
    with pytest.raises(ValueError):p.assign_cavity(i.id,c,mapping(c))
    with pytest.raises(ValueError):CavityLibrary(tmp_path).save(c)
    assert i.cavity_ref is None


def test_revision_increment_unchanged_save_and_old_revision_rejection(tmp_path):
    library=CavityLibrary(tmp_path);c=library.save(cavity());same=library.save(c)
    assert same.revision==1
    edited=deepcopy(c);edited.description='Edited engineering description'
    saved=library.save(edited);assert saved.id==c.id and saved.revision==2 and c.revision==1
    with pytest.raises(ValueError,match='revision'):library.save(c)
    fresh=saved.duplicate('New copy');assert library.save(fresh).revision==1


def test_shared_snapshot_edit_mapping_safety_and_safe_deletion(tmp_path):
    p=Project();d=component();a=p.add_instance(d);b=p.add_instance(d);library=CavityLibrary(tmp_path);c=library.save(cavity())
    for i in (a,b):p.assign_cavity(i.id,c,mapping(c))
    with pytest.raises(ValueError,match='used'):library.delete(c.id,p)
    edited=deepcopy(c);edited.profile.vertices[-1].z=12;updated=library.save(edited);p.update_cavity(updated)
    assert a.cavity_ref==b.cavity_ref==c.id and p.cavities[c.id].revision==2
    before=p.to_dict();edited=deepcopy(updated);edited.interfaces=[]
    with pytest.raises(ValueError):p.update_cavity(edited)
    assert p.to_dict()==before
    p.remove_cavity_assignment(a.id);p.remove_cavity_assignment(b.id);library.delete(c.id,p)
    assert c.id not in CavityLibrary(tmp_path).definitions


def test_portable_snapshot_missing_library_and_revision_mismatch_no_overwrite(tmp_path):
    p=Project();i=p.add_instance(component());lib=CavityLibrary(tmp_path/'library');c=lib.save(cavity());p.assign_cavity(i.id,c,mapping(c))
    path=tmp_path/'project.json';p.save(path);missing=CavityLibrary(tmp_path/'missing');reopened=Project.load(path)
    assert reopened.to_dict()==p.to_dict() and 'Missing' in missing.status(reopened,c.id)
    assert reopened.cavities[c.id].interfaces[0].direction==(0,-1,0)
    edited=deepcopy(c);edited.description='Newer library';new=lib.save(edited)
    old=Project.load(path)
    assert 'revision 2' in lib.status(old,c.id) and old.cavities[c.id].revision==1
    assert lib.definitions[c.id].description=='Newer library'
    with pytest.raises(ValueError):old.assign_cavity(i.id,new,mapping(new))
    old.update_cavity(new);assert old.cavities[c.id].revision==2


def test_assignment_undo_redo_copy_paste_and_snapshot_reference():
    p=Project();i=p.add_instance(component());history=ProjectHistory(p);c=cavity();p.assign_cavity(i.id,c,mapping(c));history.record(p)
    assert history.undo().instances[i.id].cavity_ref is None
    p=history.redo();assert p.instances[i.id].cavity_ref==c.id
    copied=p.copy_subgraph([i.id]);added=p.paste_subgraph(copied)
    assert p.instances[added[0]].cavity_ref==c.id and len(p.cavities)==1
    other=Project();new=other.paste_subgraph(copied);assert other.instances[new[0]].port_mapping==mapping(c)
    p.cavities[c.id].description='New project geometry metadata'
    added=p.paste_subgraph(copied);assert p.cavities[c.id].description=='New project geometry metadata'


def test_bad_clipboard_rolls_back_transaction():
    p=Project();i=p.add_instance(component());c=cavity();p.assign_cavity(i.id,c,mapping(c));clipboard=p.copy_subgraph([i.id])
    clipboard['instances'][0]['port_mapping']={};before=p.to_dict()
    with pytest.raises(ValueError):p.paste_subgraph(clipboard)
    assert p.to_dict()==before


def test_legacy_import_is_explicit_per_instance_idempotent_and_preserves_geometry(tmp_path):
    p=Project();d=check_valve_definition();a=p.add_instance(d,name='CV1');b=p.add_instance(d,name='CV2')
    original=p.to_dict();lib=CavityLibrary(tmp_path);one,map_one=lib.import_legacy(p,a.id);again,_=lib.import_legacy(p,a.id);two,map_two=lib.import_legacy(p,b.id)
    assert one.id==again.id and one.id!=two.id and len(lib.definitions)==2
    assert map_one!=map_two and one.profile.to_dict()==d.physical.cavity_profile.to_dict()
    assert p.to_dict()==original and a.cavity_ref is None and b.cavity_ref is None
    for old,new in zip(d.physical.hydraulic_interfaces,one.interfaces):
        for field in ('z_mm','r_mm','nominal_connection_diameter_mm','direction','section','section_rotation_deg','preview_length_mm','preview_mode'):
            assert getattr(old,field)==getattr(new,field)
    with pytest.raises(ValueError):p.assign_cavity(a.id,one,map_one) # Legacy open profile stays explicit invalid.
    one.description='Imported user edit';saved=lib.save(one,allow_legacy=True)
    assert lib.import_legacy(p,a.id)[0].description=='Imported user edit'
    assert saved.revision==2


def test_duplicate_library_ids_and_invalid_count_reported(tmp_path):
    c=cavity();(tmp_path/'a.json').write_text(json.dumps(c.to_dict()));(tmp_path/'b.json').write_text(json.dumps(c.to_dict()))
    lib=CavityLibrary(tmp_path);assert len(lib.definitions)==1 and len(lib.errors)==1
    data=c.to_dict();data['port_count']=0;(tmp_path/'bad.json').write_text(json.dumps(data))
    assert len(CavityLibrary(tmp_path).errors)==2


def test_missing_snapshot_and_corrupted_mapping_rejected():
    p=Project();i=p.add_instance(component());c=cavity();p.assign_cavity(i.id,c,mapping(c));data=p.to_dict()
    data['cavity_definitions']=[]
    with pytest.raises(ValueError,match='snapshot'):Project.from_dict(data)
    data=p.to_dict();data['component_instances'][0]['port_mapping']={}
    with pytest.raises(ValueError):Project.from_dict(data)


def test_graph_exports_assignments_without_changing_connectivity():
    p=Project();d=component();a=p.add_instance(d);b=p.add_instance(d,x=200);p.connect(p.node_for(a.id,'P0').id,p.node_for(b.id,'P0').id)
    before=export_graph(p);c=cavity();p.assign_cavity(a.id,c,mapping(c));after=export_graph(p)
    assert after['routing_connections']==before['routing_connections'] and after['nodes']==before['nodes']
    assert after['schema_version']==7 and after['component_instances'][0]['cavity_ref']==c.id
    assert after['cavity_definitions']==[c.to_dict()]


def test_portable_assignment_example_has_distinct_cavities_and_stable_topology():
    root=Path(__file__).resolve().parents[1];p=Project.load(root/'examples/instance_cavities.amcad.json')
    a,b=p.instances.values();assert a.name=='R' and b.name=='RET' and a.definition_id==b.definition_id
    assert a.cavity_ref!=b.cavity_ref and len(p.connections)==1 and len(p.cavities)==2
    assert all(d.physical.cavity_type=='NONE' for d in p.definitions.values())
    assert export_graph(p)==json.loads((root/'examples/instance_cavities.graph.json').read_text())
