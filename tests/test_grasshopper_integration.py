"""Separate export, exact features, topology and GH placement persistence."""
import ast
import json
from copy import deepcopy
from pathlib import Path
import pytest
from core.project import Project
from core.grasshopper_export import export_grasshopper,save_grasshopper
from integrations.grasshopper.make_demo import demo_project,stable
from integrations.grasshopper import amcad_runtime as runtime
from ui.main_window import MainWindow
from test_cavity_library_ui import close_window

ROOT=Path(__file__).resolve().parents[1]


def test_export_complete_independent_instances_and_unchanged_source(tmp_path):
    p=demo_project();before=p.to_dict();data=export_grasshopper(p)
    assert data['schema']=='amcad.grasshopper' and data['schema_version']==1 and data['units']=='mm'
    assert len(data['instances'])==2 and len(data['cavities'])==1 and len(data['excluded_instances'])==2
    assert data['instances'][0]['cavity_id']==data['instances'][1]['cavity_id']
    assert data['instances'][0]['id']!=data['instances'][1]['id']
    c=data['cavities'][0];source=p.cavities[c['id']]
    assert c['profile']==source.profile.to_dict()
    assert [v['corner']['type'] for v in c['profile']['vertices']].count('FILLET')==1
    assert next(v for v in c['profile']['vertices'] if v['corner']['type']=='CHAMFER')['corner']['angle_deg']==30
    arc=next(s for s in c['segments'] if s['kind']=='arc');assert arc['radius']==.5
    assert {m['id'] for m in c['interfaces']}=={m.id for m in source.interfaces}
    assert {m['section']['type'] for m in c['interfaces']}=={'CIRCLE','SLOT'}
    for m in c['interfaces']:
        assert m['source']['id']==m['id'] and len(m['position_mm'])==3 and len(m['section_u'])==3
    assert p.to_dict()==before
    path=tmp_path/'handoff.json';save_grasshopper(p,path);assert runtime.load_export(path)==data
    assert export_grasshopper(Project.from_dict(before))==data


def test_schematic_coordinates_and_rotation_never_control_physical_placement():
    p=demo_project();before=export_grasshopper(p)
    for i in p.instances.values():i.x=98765;i.y=-56789;i.rotation=270
    p.update_geometry();after=export_grasshopper(p);assert after==before
    stored=runtime.reconcile_placements(after,runtime.load_placements(None,after['project']['id']))
    assert all(v==runtime.pose() for v in stored['placements'].values())
    assert all(not {'x','y','rotation','placement'}.intersection(i) for i in after['instances'])


def test_junction_connectivity_boundary_and_internal_relationship_semantics():
    data=export_grasshopper(demo_project());nets=data['connectivity']['nets']
    shared=next(n for n in nets if len(n['terminals'])==2)
    assert {t['instance_id'] for t in shared['terminals']}=={stable('instance:CV1'),stable('instance:CV2')}
    assert len(shared['boundary_node_ids'])==1
    boundary=next(n for n in data['connectivity']['nodes'] if n['id']==shared['boundary_node_ids'][0])
    assert boundary['instance_id']==stable('instance:Boundary') and boundary['physical_terminal'] is None
    assert len(nets)==3 and len(data['connectivity']['edges'])==3
    for i in data['instances']:
        assert {n['physical_terminal']['interface_id'] for n in data['connectivity']['nodes'] if n['instance_id']==i['id']}==set(i['port_mapping'].values())
    # Changing name affects display only, never persistent net/terminal identity.
    p=demo_project();p.rename(stable('instance:CV1'),'Renamed valve');renamed=export_grasshopper(p)
    assert renamed['connectivity']['nets']==nets


@pytest.mark.parametrize('bad',[
    'schema','version','units','geometry','corner','arc_radius','arc_end','missing_feature',
    'chamfer_length','chamfer_angle','mapping','revision','unknown_interface','topology','boundary','schematic_position','nan'])
def test_import_rejects_unsupported_or_inconsistent_data(bad):
    data=export_grasshopper(demo_project());c=data['cavities'][0]
    if bad=='schema':data['schema']='amcad.project'
    elif bad=='version':data['schema_version']=99
    elif bad=='units':data['units']='inch'
    elif bad=='geometry':c['geometry_type']='FREEFORM'
    elif bad=='corner':c['profile']['vertices'][1]['corner']['type']='SPLINE'
    elif bad=='arc_radius':next(s for s in c['segments'] if s['kind']=='arc')['radius']=.6
    elif bad=='arc_end':next(s for s in c['segments'] if s['kind']=='arc')['end'][0]+=1
    elif bad=='missing_feature':c['segments']=[s for s in c['segments'] if s['kind']!='arc']
    elif bad=='chamfer_length':next(v for v in c['profile']['vertices'] if v['corner']['type']=='CHAMFER')['corner']['length_mm']=.8
    elif bad=='chamfer_angle':next(v for v in c['profile']['vertices'] if v['corner']['type']=='CHAMFER')['corner']['angle_deg']=45
    elif bad=='mapping':data['instances'][0]['port_mapping']={}
    elif bad=='revision':data['instances'][0]['cavity_revision']=2
    elif bad=='unknown_interface':data['connectivity']['nodes'][0]['physical_terminal']['interface_id']='missing'
    elif bad=='topology':data['connectivity']['nets'].pop()
    elif bad=='boundary':next(n for n in data['connectivity']['nets'] if n['boundary_node_ids'])['boundary_node_ids']=[]
    elif bad=='schematic_position':data['instances'][0]['x']=123
    else:c['interfaces'][0]['position_mm'][0]=float('nan')
    with pytest.raises(runtime.ImportErrorDetail):runtime.validate_export(data)


@pytest.mark.parametrize('rotation,point,expected',[
    ([90,0,0],[0,1,0],[0,0,1]),([0,90,0],[0,0,1],[1,0,0]),
    ([0,0,90],[1,0,0],[0,1,0]),([90,90,90],[1,0,0],[0,0,-1])])
def test_right_handed_rotation_order_and_translation(rotation,point,expected):
    transform=runtime.matrix(runtime.pose([10,20,30],rotation))
    assert runtime.transform_vector(transform,point)==pytest.approx(expected)
    assert runtime.transform_point(transform,point)==pytest.approx([a+b for a,b in zip(expected,[10,20,30])])


def test_shared_cavity_interfaces_transform_independently_and_without_metadata_loss():
    c=export_grasshopper(demo_project())['cavities'][0];before=deepcopy(c)
    a=runtime.world_interfaces(c,'A',runtime.pose());b=runtime.world_interfaces(c,'B',runtime.pose([30,10,5],[15,30,90]))
    assert c==before and a[0]['position_mm']!=b[0]['position_mm']
    for old,new in zip(c['interfaces'],b):
        assert new['id']==old['id'] and new['instance_id']=='B'
        assert new['section']==old['section'] and new['source']==old['source']
        assert new['position_mm']==pytest.approx(runtime.transform_point(runtime.matrix(runtime.pose([30,10,5],[15,30,90])),old['position_mm']))
        assert sum(v*v for v in new['direction'])==pytest.approx(1)
        assert sum(a*b for a,b in zip(new['section_u'],new['direction']))==pytest.approx(0,abs=1e-12)


def test_placement_roundtrip_reordering_revision_changes_missing_and_new_ids(tmp_path):
    export=export_grasshopper(demo_project());stored=runtime.reconcile_placements(export,runtime.load_placements(None,export['project']['id']))
    first,second=[i['id'] for i in export['instances']];stored['placements'][second]=runtime.pose([30,10,5],[15,30,90])
    path=tmp_path/'poses.json';runtime.save_placements(path,stored)
    reloaded=runtime.load_placements(path,export['project']['id']);assert reloaded==stored
    updated=deepcopy(export);updated['instances'].reverse();updated['cavities'][0]['revision']=2
    for i in updated['instances']:i['cavity_revision']=2
    assert runtime.reconcile_placements(updated,reloaded)==stored
    updated['instances']=[i for i in updated['instances'] if i['id']!=second]
    assert runtime.reconcile_placements(updated,reloaded)['placements'][second]==stored['placements'][second]
    updated['instances'].append({'id':'new-instance'})
    assert runtime.reconcile_placements(updated,reloaded)['placements']['new-instance']==runtime.pose()
    with pytest.raises(runtime.ImportErrorDetail,match='another project'):runtime.load_placements(path,'other-project')


def test_explicit_gh_list_parameters_never_broadcast():
    data=export_grasshopper(demo_project());stored=runtime.reconcile_placements(data,runtime.load_placements(None,data['project']['id']))
    ids=[i['id'] for i in data['instances']]
    runtime.apply_parameters(data,stored,ids,{'X':[2,40],'Ry':[0,30]})
    assert [stored['placements'][i]['translation_mm'][0] for i in ids]==[2,40]
    assert stored['placements'][ids[1]]['rotation_deg']==[0,30,0]
    with pytest.raises(runtime.ImportErrorDetail,match='no implicit broadcasting'):runtime.apply_parameters(data,stored,ids,{'Z':[3]})
    with pytest.raises(runtime.ImportErrorDetail,match='unique'):runtime.apply_parameters(data,stored,['missing'],{'X':[3]})


def test_export_and_placement_writers_protect_project_and_library_data(tmp_path):
    p=demo_project();source=tmp_path/'project.amcad.json';p.save(source);before=source.read_bytes()
    with pytest.raises(ValueError,match='cannot overwrite'):save_grasshopper(p,source)
    assert source.read_bytes()==before
    c=next(iter(p.cavities.values()));cavity_path=tmp_path/'library-cavity.json';cavity_path.write_text(json.dumps(c.to_dict()));before=cavity_path.read_bytes()
    with pytest.raises(ValueError):save_grasshopper(p,cavity_path)
    stored=runtime.reconcile_placements(export_grasshopper(p),runtime.load_placements(None,p.metadata['id']))
    with pytest.raises(runtime.ImportErrorDetail):runtime.save_placements(cavity_path,stored)
    assert cavity_path.read_bytes()==before
    output=tmp_path/'export.json';save_grasshopper(p,output);before=output.read_bytes()
    with pytest.raises(runtime.ImportErrorDetail,match='separate'):runtime.save_placements(output,stored,output)
    assert output.read_bytes()==before


def test_gui_export_action_uses_separate_format_and_does_not_dirty_project(qapp,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    w=MainWindow(tmp_path/'components');w.project=demo_project();w.sync_project();w.history.mark_saved(w.project)
    try:
        path=tmp_path/'gh.json';monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args,**kwargs:(str(path),'JSON'))
        w.actions['grasshopper_export'].trigger()
        assert runtime.load_export(path)['project']['id']==w.project.metadata['id']
        assert not w.history.is_dirty(w.project) and not w.library.directory.exists() and not w.cavity_library.directory.exists()
    finally:close_window(w)


def test_shipped_demo_and_rhino_python39_source_compatibility():
    folder=ROOT/'integrations/grasshopper';data=runtime.load_export(folder/'demo.grasshopper.json')
    assert data==export_grasshopper(Project.load(folder/'demo_project.amcad.json'))
    placements=runtime.load_placements(folder/'demo.placements.json',data['project']['id'])
    assert len({tuple(p['translation_mm']) for p in placements['placements'].values()})==2
    for name in ('amcad_runtime.py','rhino_importer.py','example_component.py'):
        ast.parse((folder/name).read_text(),feature_version=(3,9))
