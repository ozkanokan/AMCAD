"""Independent edits, selection safety, persistence and Phase 1 compatibility."""
from copy import deepcopy
from pathlib import Path
import ast
import json
import pytest
from core.grasshopper_export import export_grasshopper
from integrations.grasshopper.make_phase2_demo import project_with_instances
from integrations.grasshopper.make_demo import stable
from integrations.grasshopper.placement_controller import PlacementController
from integrations.grasshopper import amcad_runtime as runtime

ROOT=Path(__file__).resolve().parents[1]


def data(count=7):return export_grasshopper(project_with_instances(count))


def apply(model,instance_id,translation,rotation=None):
    model.select(instance_id);model.apply_selected(translation,rotation or [0,0,0],model.selection_token)


@pytest.mark.parametrize('count',[7,20,50])
def test_independent_selection_apply_and_scalable_name_catalog(count,tmp_path):
    exported=data(count);model=PlacementController(exported,tmp_path/'poses.json');before=model.snapshot()
    a,b=stable('instance:CV1'),stable('instance:CV2')
    apply(model,a,[50,0,0]);apply(model,b,[0,30,0]);model.select(a)
    assert model.placement(a)['translation_mm']==[50,0,0] and model.placement(b)['translation_mm']==[0,30,0]
    for key,value in before['placements'].items():
        if key not in (a,b):assert model.placement(key)==value
    assert len(model.catalog())==count and [r['name'] for r in model.catalog()][:3]==['CV1','CV2','CV3']
    assert {r['name'] for r in model.catalog('cv2')}=={'CV'+str(i) for i in range(1,count+1) if str(i).startswith('2')}
    assert exported==data(count)


def test_selection_changes_do_not_apply_stale_values_even_after_returning_to_a():
    model=PlacementController(data());a,b=stable('instance:CV1'),stable('instance:CV2')
    apply(model,a,[50,0,0]);old=model.selection_token
    assert model.select(b)==runtime.pose();before=model.snapshot()
    with pytest.raises(ValueError,match='Selection changed'):model.apply_selected([50,0,0],[0,0,0],old)
    assert model.snapshot()==before
    model.select(a)
    with pytest.raises(ValueError):model.apply_selected([99,0,0],[0,0,0],old)
    assert model.placement(a)['translation_mm']==[50,0,0]


def test_seven_instance_acceptance_save_reopen_phase1_loader(tmp_path):
    exported=data();path=tmp_path/'poses.json';model=PlacementController(exported,path)
    a,b=stable('instance:CV1'),stable('instance:CV2')
    apply(model,a,[50,0,0]);apply(model,b,[0,30,0]);model.select(a)
    assert model.placement(a)['translation_mm'][0]==50 and model.placement(b)['translation_mm'][1]==30
    model.save();assert not model.dirty
    phase1=runtime.load_placements(path,exported['project']['id'])
    reopened=PlacementController(exported,path);assert reopened.snapshot()==phase1==model.snapshot()
    assert len(phase1['placements'])==7 and phase1['schema_version']==1
    apply(reopened,a,[80,0,0]);assert reopened.dirty;reopened.reload()
    assert not reopened.dirty and reopened.placement(a)['translation_mm'][0]==50
    assert reopened.placement(b)['translation_mm'][1]==30


def test_revision_rename_reorder_and_temporarily_missing_instance_preserve_ids():
    project=project_with_instances();exported=export_grasshopper(project);model=PlacementController(exported)
    a=stable('instance:CV1');apply(model,a,[50,2,3],[10,20,30]);token=model.selection_token
    project.rename(a,'Different readable name');cavity=next(iter(project.cavities.values()));cavity.revision+=1
    changed=export_grasshopper(project);changed['instances'].reverse();model.refresh_export(changed)
    assert model.placement(a)==runtime.pose([50,2,3],[10,20,30]) and model.selection_token==token
    assert next(r for r in model.catalog() if r['id']==a)['name']=='Different readable name'
    assert not model.refresh_export(deepcopy(changed))
    project.remove_cavity_assignment(a);model.refresh_export(export_grasshopper(project))
    assert model.selected_id is None and model.placement(a)==runtime.pose([50,2,3],[10,20,30])
    model.refresh_export(changed);model.select(a);assert model.placement(a)['translation_mm'][0]==50


def test_new_instances_identity_orphans_survive_saving_and_reload(tmp_path):
    model=PlacementController(data(7),tmp_path/'poses.json');a=stable('instance:CV1');apply(model,a,[50,0,0])
    model.refresh_export(data(20))
    for i in range(8,21):assert model.placement(stable('instance:CV'+str(i)))==runtime.pose()
    model.refresh_export(data(7));assert len(model.snapshot()['placements'])==20
    model.save();again=PlacementController(data(7),model.placement_path);assert again.snapshot()==model.snapshot()
    again.refresh_export(data(20));assert len(again.parameters())==20 and again.placement(a)['translation_mm'][0]==50


def test_update_many_transaction_and_external_selected_update_invalidates_editor_token():
    model=PlacementController(data());a,b=stable('instance:CV1'),stable('instance:CV2');model.select(a);token=model.selection_token;before=model.snapshot()
    with pytest.raises(ValueError):model.update_many({a:runtime.pose([50,0,0]),'missing':runtime.pose()})
    assert model.snapshot()==before
    with pytest.raises(ValueError):model.update_many({a:runtime.pose([50,0,0]),b:{'translation_mm':[0,float('nan'),0],'rotation_deg':[0,0,0]}})
    assert model.snapshot()==before
    assert model.update_many({a:runtime.pose([50,0,0]),b:runtime.pose([0,30,0])})
    with pytest.raises(ValueError):model.apply_selected([0,0,0],[0,0,0],token)
    assert not model.update_many({a:runtime.pose([50,0,0])})


def test_programmatic_parameters_and_interfaces_reuse_phase1_transform_contract():
    exported=data();model=PlacementController(exported);a=stable('instance:CV1');apply(model,a,[10,20,30],[90,0,0])
    record=next(r for r in model.parameters() if r['instance_id']==a)
    assert record['matrix']==runtime.matrix(runtime.pose([10,20,30],[90,0,0]))
    assert runtime.transform_point(record['matrix'],[0,1,0])==pytest.approx([10,20,31])
    cavity=exported['cavities'][0];world=runtime.world_interfaces(cavity,a,model.placement(a))
    for old,new in zip(cavity['interfaces'],world):
        assert new['position_mm']==pytest.approx(runtime.transform_point(record['matrix'],old['position_mm']))
        for field in ('direction','section_u','section_v'):assert new[field]==pytest.approx(runtime.transform_vector(record['matrix'],old[field]))
    record['translation_mm'][0]=999;assert model.placement(a)['translation_mm'][0]==10
    snapshot=model.snapshot();snapshot['placements'][a]['translation_mm'][0]=999;assert model.placement(a)['translation_mm'][0]==10


def test_reload_missing_invalid_or_wrong_project_is_nondestructive(tmp_path):
    path=tmp_path/'poses.json';model=PlacementController(data(),path);a=stable('instance:CV1');apply(model,a,[50,0,0]);before=model.snapshot()
    with pytest.raises(ValueError,match='No saved'):model.reload()
    assert model.snapshot()==before
    path.write_text('{broken')
    with pytest.raises(ValueError):model.reload()
    assert model.snapshot()==before
    wrong=deepcopy(before);wrong['project_id']='another';path.write_text(json.dumps(wrong))
    with pytest.raises(ValueError):model.reload()
    assert model.snapshot()==before


def test_phase1_placement_files_geometry_export_and_library_protection(tmp_path):
    folder=ROOT/'integrations/grasshopper';exported=runtime.load_export(folder/'demo.grasshopper.json')
    path=tmp_path/'existing-poses.json';path.write_bytes((folder/'demo.placements.json').read_bytes());before=path.read_bytes()
    model=PlacementController(exported,path);assert not model.dirty and path.read_bytes()==before
    model.select(exported['instances'][0]['id']);model.save();assert runtime.load_placements(path,exported['project']['id'])==model.snapshot()
    source=tmp_path/'export.json';source.write_text(json.dumps(exported));before=source.read_bytes()
    blocked=PlacementController(exported,export_path=source);blocked.placement_path=str(source)
    with pytest.raises(ValueError,match='separate'):blocked.save()
    assert source.read_bytes()==before


def test_shipped_seven_instance_demo_and_python39_compatibility():
    folder=ROOT/'integrations/grasshopper';exported=runtime.load_export(folder/'phase2-seven.grasshopper.json')
    assert exported==data(7) and len(exported['instances'])==7
    stored=runtime.load_placements(folder/'phase2-seven.placements.json',exported['project']['id'])
    assert len(PlacementController(exported,stored=stored).parameters())==7
    for name in ('placement_controller.py','placement_editor.py','controller_component.py'):
        ast.parse((folder/name).read_text(),feature_version=(3,9))


def test_save_reload_edit_commands_fire_on_edges_and_reject_ambiguous_save_reload():
    from integrations.grasshopper.placement_controller import CommandEdges
    edges=CommandEdges();assert edges.consume({'Save':True,'Reload':False,'Edit':False})==['Save']
    assert edges.consume({'Save':True,'Reload':False,'Edit':False})==[]
    assert edges.consume({'Save':False,'Reload':False,'Edit':True})==['Edit']
    assert edges.consume({'Save':False,'Reload':False,'Edit':True})==[]
    edges.consume({'Save':False,'Reload':False,'Edit':False})
    with pytest.raises(ValueError,match='separately'):edges.consume({'Save':True,'Reload':True,'Edit':False})
    assert edges.consume({'Save':True,'Reload':True,'Edit':False})==[]


def test_reload_invalidates_old_field_token_and_does_not_change_geometry_version(tmp_path):
    model=PlacementController(data(),tmp_path/'poses.json');a=stable('instance:CV1');model.select(a);model.save();token=model.selection_token;version=model.version
    model.reload();assert model.version==version and model.selection_token!=token
    with pytest.raises(ValueError):model.apply_selected([50,0,0],[0,0,0],token)
    before=model.version;model.select(stable('instance:CV2'));assert model.version==before


def test_extra_existing_placement_metadata_survives_updates_and_wrong_project_rejected():
    exported=data();stored=runtime.reconcile_placements(exported,runtime.load_placements(None,exported['project']['id']));a=stable('instance:CV1')
    stored['note']='Preserve existing metadata';stored['placements'][a]['note']='datum'
    model=PlacementController(exported,stored=stored);apply(model,a,[50,0,0])
    assert model.snapshot()['note']=='Preserve existing metadata' and model.placement(a)['note']=='datum'
    different=deepcopy(exported);different['project']['id']='other';before=model.snapshot()
    with pytest.raises(ValueError,match='another project'):model.refresh_export(different)
    assert model.snapshot()==before
