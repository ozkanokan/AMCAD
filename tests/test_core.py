import copy
import pytest
from examples.create_demo import create_demo
from core.project import Project
from core.graph import export_graph


def test_acceptance_round_trip(tmp_path):
    p = create_demo()
    original_edges = [(c.from_node_id,c.to_node_id) for c in p.connections.values()]
    rv = next(i for i in p.instances.values() if i.name == 'RV1')
    p.rename(rv.id, 'Relief1')
    rv.x += 40; rv.y -= 10; rv.rotation = 90
    p.save(tmp_path / 'project.json')
    reopened = Project.load(tmp_path / 'project.json')
    assert reopened.to_dict() == p.to_dict()
    assert [(c.from_node_id,c.to_node_id) for c in reopened.connections.values()] == original_edges
    graph = export_graph(reopened)
    assert len(graph['nodes']) == 11
    assert len(graph['routing_connections']) == 5
    assert len(graph['junctions']) == 3
    assert len(graph['junction_instances']) == 1
    assert len(graph['component_internal_relationships']) == 3
    assert graph['component_internal_relationships'][0]['relationship'] == 'RELIEF_VALVE'
    assert any(n['label']=='Relief1.IN' for n in graph['nodes'])


def test_delete_copy_duplicate_and_undo_snapshot():
    p = create_demo(); before = p.to_dict()
    edge = next(iter(p.connections.values()))
    with pytest.raises(ValueError): p.connect(edge.to_node_id,edge.from_node_id)
    with pytest.raises(ValueError): p.connect(edge.from_node_id,edge.from_node_id)
    ids = p.paste_subgraph(p.copy_subgraph(p.instances))
    assert len(ids)==5 and len(p.connections)==10
    assert len(p.nodes)==22
    p.remove_instance(ids[0]); p.validate()
    assert Project.from_dict(before).to_dict()==before


@pytest.mark.parametrize('mutation', ['endpoint','version','node','duplicate','rotation','junction'])
def test_reject_invalid_project(mutation):
    d = copy.deepcopy(create_demo().to_dict())
    if mutation=='endpoint': d['connections'][0]['to_node_id']='missing'
    if mutation=='version': d['schema_version']=999
    if mutation=='node': d['nodes'].pop()
    if mutation=='duplicate': d['nodes'].append(d['nodes'][0])
    if mutation=='rotation': d['component_instances'][0]['rotation']=17
    if mutation=='junction': d['junctions']=[]
    with pytest.raises(ValueError): Project.from_dict(d)
