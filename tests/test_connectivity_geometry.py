import copy
import json
from dataclasses import asdict
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from core.component_definition import ComponentDefinition
from core.connection import Connection
from core.geometry import LEAD_LENGTH, SIDE_VECTORS, rotated_side, wire_points
from core.graph import export_graph
from core.history import ProjectHistory
from core.junction import junction_definition
from core.library import ComponentLibrary
from core.port import Node, PortDefinition, new_id
from core.project import Project
from ui.main_window import MainWindow

SAMPLE = Path(__file__).resolve().parents[1] / 'tests/fixtures/c1_r.v1.json'


def assert_orthogonal_leads(points, source_side, target_side):
    assert len(points) >= 3
    for a, b in zip(points, points[1:]):
        assert a != b
        assert a[0] == pytest.approx(b[0]) or a[1] == pytest.approx(b[1])
    for endpoint, lead_end, side in ((points[0], points[1], source_side),
                                      (points[-1], points[-2], target_side)):
        vector = SIDE_VECTORS[side]
        assert (lead_end[0]-endpoint[0], lead_end[1]-endpoint[1]) == pytest.approx(
            (vector[0]*LEAD_LENGTH, vector[1]*LEAD_LENGTH))
    # A lead may turn or continue outward, but must not immediately backtrack.
    for lead_end, next_point, side in ((points[1], points[2], source_side),
                                       (points[-2], points[-3], target_side)):
        vx, vy = SIDE_VECTORS[side]
        assert (next_point[0]-lead_end[0])*vx + (next_point[1]-lead_end[1])*vy >= -1e-9


@pytest.mark.parametrize('source_side', SIDE_VECTORS)
@pytest.mark.parametrize('target_side', SIDE_VECTORS)
@pytest.mark.parametrize('target', [(240,120),(-240,-120),(240,0),(0,240),(10,0),(0,0)])
def test_wire_side_leads_and_orthogonal_segments(source_side,target_side,target):
    points = wire_points((0,0),source_side,target,target_side)
    assert points[0] == (0,0) and points[-1] == target
    assert_orthogonal_leads(points,source_side,target_side)


@pytest.mark.parametrize('side,expected', [('TOP','RIGHT'),('RIGHT','BOTTOM'),('BOTTOM','LEFT'),('LEFT','TOP')])
def test_clockwise_side_rotation(side,expected):
    assert rotated_side(side,90) == expected
    assert rotated_side(side,360) == side


def path_points(wire):
    path=wire.logical_path
    return [(path.elementAt(i).x,path.elementAt(i).y) for i in range(path.elementCount())]


@pytest.mark.parametrize('turns', [1,2,3,4], ids=['90deg','180deg','270deg','360deg'])
def test_connected_in_out_identity_through_rotation(qapp,tmp_path,turns):
    definition=ComponentDefinition('two-port','Two Port','V','Generic',[
        PortDefinition('IN','IN',side='LEFT'),PortDefinition('OUT','OUT',side='RIGHT')])
    w=MainWindow(tmp_path/'library')
    w.project=Project('Connected IN / OUT')
    a=w.project.add_instance(definition,0,0,'A')
    b=w.project.add_instance(definition,300,160,'B')
    for port_id in ('IN','OUT'):
        w.project.connect(w.project.node_for(a.id,port_id).id,w.project.node_for(b.id,port_id).id)
    original=[{k:v for k,v in asdict(c).items() if k!='schematic_geometry'} for c in w.project.connections.values()]
    original_nodes=[asdict(n) for n in w.project.nodes.values()]
    w.history=ProjectHistory(w.project); w.sync_project(); w.show(); qapp.processEvents()
    w.activateWindow(); w.view.setFocus(); qapp.processEvents()
    w.view.component_items[a.id].setSelected(True)
    initial_positions={p: w.view.port_items[w.project.node_for(a.id,p).id].scenePos() for p in ('IN','OUT')}
    for step in range(1,turns+1):
        QTest.keyClick(w.view,Qt.Key_R,Qt.ControlModifier); qapp.processEvents()
        assert w.project.instances[a.id].rotation == (step*90)%360
        assert [{k:v for k,v in asdict(c).items() if k!='schematic_geometry'} for c in w.project.connections.values()] == original
        assert [asdict(n) for n in w.project.nodes.values()] == original_nodes
        for c in w.project.connections.values():
            assert c.from_component_instance_id==a.id and c.to_component_instance_id==b.id
            assert c.from_port_id==c.to_port_id and c.from_port_id in {'IN','OUT'}
            source=w.view.port_items[c.from_node_id]; target=w.view.port_items[c.to_node_id]
            source_side=rotated_side(source.side,(step*90)%360)
            target_side=target.side
            points=path_points(w.view.wires[c.id])
            assert points[0] == pytest.approx((source.scenePos().x(),source.scenePos().y()))
            assert points[-1] == pytest.approx((target.scenePos().x(),target.scenePos().y()))
            assert_orthogonal_leads(points,source_side,target_side)
            initial=initial_positions[c.from_port_id]
            expected=[(initial.x(),initial.y()),(-initial.y(),initial.x()),
                      (-initial.x(),-initial.y()),(initial.y(),-initial.x())][step%4]
            assert (source.scenePos().x(),source.scenePos().y())==pytest.approx(expected)
    w.save_to(tmp_path/'rotated.json')
    loaded=Project.load(tmp_path/'rotated.json')
    assert loaded.to_dict()==w.project.to_dict()
    assert [{k:v for k,v in asdict(c).items() if k!='schematic_geometry'} for c in loaded.connections.values()]==original
    assert [dict((k,c[k]) for k in original[0]) for c in export_graph(loaded)['routing_connections']]==original
    w.undo(); assert w.project.instances[a.id].rotation==((turns-1)*90)%360
    w.redo(); assert w.project.instances[a.id].rotation==(turns*90)%360
    w.history.mark_saved(w.project); w.close()


@pytest.mark.parametrize('ways', [3,4])
def test_junction_capacity_copy_roundtrip_and_reuse(tmp_path,ways):
    p=Project(); j=p.add_instance(junction_definition(ways))
    external=ComponentLibrary(tmp_path/'empty-library').definitions['external-port']
    outside=[p.add_instance(external,name=f'E{i}') for i in range(ways+1)]
    ports=[p.node_for(j.id,port.id).id for port in p.definitions[j.definition_id].ports]
    assert len(ports)==ways
    for i,node_id in enumerate(ports):
        # Alternate endpoint order to exercise both occupancy paths.
        endpoint=p.node_for(outside[i].id,'port').id
        p.connect(*( (node_id,endpoint) if i%2 else (endpoint,node_id) ))
    before=p.to_dict()
    for node_id in ports:
        with pytest.raises(ValueError,match='occupied'):
            p.connect(p.node_for(outside[-1].id,'port').id,node_id)
        assert p.to_dict()==before
    first=next(iter(p.connections)); del p.connections[first]
    p.connect(ports[0],p.node_for(outside[-1].id,'port').id)
    p.save(tmp_path/'junction.json')
    assert Project.load(tmp_path/'junction.json').to_dict()==p.to_dict()
    copied=p.paste_subgraph(p.copy_subgraph(p.instances))
    pasted_j=next(p.instances[i] for i in copied if p.definitions[p.instances[i].definition_id].symbol['kind']=='junction')
    assert len([n for n in p.nodes.values() if n.instance_id==pasted_j.id])==ways
    p.validate()
    graph=export_graph(p)
    assert len(graph['junction_instances'])==2
    assert all(j['capacity']==ways for j in graph['junction_instances'])
    assert len(graph['component_internal_relationships'])==2*(ways-1)


@pytest.mark.parametrize('ways', [3,4])
def test_junction_canvas_ports_and_occupied_click(qapp,tmp_path,ways):
    w=MainWindow(tmp_path/'library'); w.show(); qapp.processEvents()
    assert 'junction' not in w.available_definitions
    w.add_junction(ways)
    j=next(iter(w.project.instances.values()))
    item=w.view.component_items[j.id]
    assert len(item.ports)==ways and len({(p.pos().x(),p.pos().y()) for p in item.ports.values()})==ways
    ids=list(item.ports)
    for i in range(ways+1): w.place('external-port',180+i*70,100)
    externals=[i for i in w.project.instances.values() if i.id!=j.id]
    for index,port in enumerate(ids):
        w.view.port_clicked(port); w.view.port_clicked(w.project.node_for(externals[index].id,'port').id)
    before=w.project.to_dict()
    messages=[]; w.view.message.connect(messages.append)
    w.view.port_clicked(w.project.node_for(externals[-1].id,'port').id); w.view.port_clicked(ids[0])
    assert w.project.to_dict()==before and 'occupied' in messages[-1]
    w.delete_selection()  # Last placement was selected; no wires may cross-connect implicitly.
    w.history.mark_saved(w.project); w.close()


def legacy_sample(branches=3):
    data=json.loads(SAMPLE.read_text())
    junction_node=next(n['id'] for n in data['nodes'] if n['kind']=='junction')
    incident=[c for c in data['connections'] if junction_node in (c['from_node_id'],c['to_node_id'])]
    for c in incident[branches:]: data['connections'].remove(c)
    external=next(i for i in data['component_instances'] if i['name']=='C1')
    for index in range(3,branches):
        instance=copy.deepcopy(external); instance.update(id=new_id(),name=f'Additional{index}',x=-400,y=index*80)
        node=Node(new_id(),instance['id'],'port','external_port')
        data['component_instances'].append(instance); data['nodes'].append(asdict(node))
        # Old connection format has no explicit instance/port reference fields.
        data['connections'].append({'id':new_id(),'from_node_id':junction_node,'to_node_id':node.id})
    return data


@pytest.mark.parametrize('branches', [0,1,2,3,4])
def test_legacy_junction_migration_preserves_connectivity_and_identity(tmp_path,branches):
    old=legacy_sample(branches)
    old_copy=copy.deepcopy(old)
    p=Project.from_dict(old)
    assert old==old_copy
    assert p.to_dict()==Project.from_dict(old).to_dict()  # Deterministic new identities.
    assert {i.id for i in p.instances.values()} >= {i['id'] for i in old['component_instances']}
    junction=next(i for i in p.instances.values() if p.definitions[i.definition_id].symbol['kind']=='junction')
    assert len(p.definitions[junction.definition_id].ports)==(4 if branches==4 else 3)
    assert {c.id for c in p.connections.values()} >= {c['id'] for c in old['connections']}
    old_nodes={n['id']:n for n in old['nodes']}
    for edge in old['connections']:
        current=p.connections[edge['id']]
        for end in ('from','to'):
            old_node=old_nodes[edge[f'{end}_node_id']]
            if old_node['instance_id']==junction.id:
                assert getattr(current,f'{end}_component_instance_id')==junction.id
            if old_node['kind']!='junction' and old_node['instance_id']!=next(i['id'] for i in old['component_instances'] if i['name']=='R'):
                assert getattr(current,f'{end}_node_id')==old_node['id']
                assert getattr(current,f'{end}_port_id')==old_node['port_id']
    p.save(tmp_path/'migrated.json'); assert Project.load(tmp_path/'migrated.json').to_dict()==p.to_dict()
    # The common junction remains one hydraulic net through internal relationships.
    graph=export_graph(p)
    jnodes=set(graph['junction_instances'][0]['port_node_ids'])
    relationships=[r for r in graph['component_internal_relationships'] if r['component_instance_id']==junction.id]
    reachable={next(iter(jnodes))}
    for _ in jnodes:
        for r in relationships:
            if r['from_node_id'] in reachable or r['to_node_id'] in reachable:
                reachable.update((r['from_node_id'],r['to_node_id']))
    assert reachable==jnodes


def test_legacy_high_degree_and_corrupt_endpoint_rejection():
    with pytest.raises(ValueError,match='more than four'):
        Project.from_dict(legacy_sample(5))
    p=Project.load(SAMPLE)
    data=p.to_dict(); data['connections'][0]['to_port_id']='other'
    with pytest.raises(ValueError,match='references disagree'):
        Project.from_dict(data)
    data=p.to_dict()
    junction=next(n for n in p.nodes.values() if n.kind=='junction')
    external=next(n for n in p.nodes.values() if n.kind=='external_port')
    edge=Connection(external.id,junction.id,from_component_instance_id=external.instance_id,from_port_id=external.port_id,
                    to_component_instance_id=junction.instance_id,to_port_id=junction.port_id)
    # Pick an unused external source with the same occupied junction endpoint.
    target=next(n for n in p.nodes.values() if n.kind=='component_port')
    edge.from_node_id=target.id; edge.from_component_instance_id=target.instance_id; edge.from_port_id=target.port_id
    data['connections'].append(asdict(edge))
    with pytest.raises(ValueError,match='occupied'):
        Project.from_dict(data)


def test_existing_sample_gui_migration_undo_copy_and_export(qapp,tmp_path):
    raw=json.loads(SAMPLE.read_text())
    w=MainWindow(tmp_path/'library'); w.load_path(SAMPLE); w.show(); qapp.processEvents()
    assert len(w.project.instances)==6 and len(w.view.wires)==6
    legacy_j=next(i for i in raw['component_instances'] if i['name']=='J1')
    j=w.project.instances[legacy_j['id']]
    assert (j.x,j.y,j.rotation)==(legacy_j['x'],legacy_j['y'],legacy_j['rotation'])
    assert len(w.view.component_items[j.id].ports)==3
    before=w.project.to_dict()
    w.select_all(); w.copy(); w.paste()
    assert len(w.project.instances)==12 and len(w.project.connections)==12
    w.undo(); assert w.project.to_dict()==before
    w.redo(); assert len(w.project.instances)==12
    w.undo(); assert w.project.to_dict()==before
    w.save_to(tmp_path/'upgraded.json')
    assert Project.load(tmp_path/'upgraded.json').to_dict()==before
    w.export_to(tmp_path/'graph.json')
    graph=json.loads((tmp_path/'graph.json').read_text())
    assert graph['schema_version']==3
    assert len(graph['routing_connections'])==6 and len(graph['junction_instances'])==2
    assert graph['junction_instances'][0]['capacity']==3
    assert SAMPLE.read_text()==json.dumps(raw,indent=2)+'\n'  # Original V1 file was not rewritten.
    w.close()
