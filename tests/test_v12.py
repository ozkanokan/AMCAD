import copy
import json
from dataclasses import asdict
from pathlib import Path
import pytest
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDockWidget, QTableWidgetItem, QDialog
from core.component_definition import ComponentDefinition
from core.port import PortDefinition, new_id, Node
from core.project import Project
from core.graph import export_graph
from core.library import ComponentLibrary
from core.history import ProjectHistory
from core.line_geometry import crossing_points, endpoint, normalize
from core.geometry import SIDE_VECTORS, LEAD_LENGTH
from ui.main_window import MainWindow
from ui.node_wizard import NodeWizard

ROOT=Path(__file__).resolve().parents[1]


def logical(c):
    return {k:v for k,v in asdict(c).items() if k!='schematic_geometry'}


def make_pair(tmp_path):
    p=Project('Manual lines')
    d=ComponentDefinition('manual','Manual','M','Generic',[
        PortDefinition('OUT','OUT',side='RIGHT'),PortDefinition('OPTIONAL','Optional',side='TOP',required=False)])
    target=ComponentDefinition('target','Target','T','Generic',[PortDefinition('IN','IN',side='LEFT')])
    a=p.add_instance(d,-220,-80); b=p.add_instance(target,220,160)
    return p,a,b,p.node_for(a.id,'OUT').id,p.node_for(b.id,'IN').id


@pytest.mark.parametrize('kind',['generic-2','external-port','junction-3','junction-4'])
@pytest.mark.parametrize('reverse',[False,True])
def test_every_port_rejects_second_external_line(tmp_path,kind,reverse):
    library=ComponentLibrary(tmp_path/'library'); p=Project()
    instance=p.add_instance(library.definitions[kind])
    a=p.node_for(instance.id,p.definitions[instance.definition_id].ports[0].id).id
    outside=[p.add_instance(library.definitions['external-port'],300+i*100,0) for i in range(2)]
    b,c=[p.node_for(i.id,'port').id for i in outside]
    first=p.connect(a,b); before=p.to_dict()
    with pytest.raises(ValueError,match='already has a line'):
        p.connect(*( (c,a) if reverse else (a,c) ))
    assert p.to_dict()==before and p.connections[first.id] is first
    del p.connections[first.id]
    p.connect(a,c); p.validate()


def test_completeness_required_optional_delete_load_and_wizard(qapp,tmp_path):
    p,a,b,source,target=make_pair(tmp_path)
    assert not p.is_complete(a.id) and p.incomplete_ports(a.id)==['OUT']
    line=p.connect(source,target)
    assert p.is_complete(a.id) and p.is_complete(b.id)
    w=MainWindow(tmp_path/'library'); w.project=p; w.history=ProjectHistory(p); w.sync_project(); w.show(); qapp.processEvents()
    assert w.dockWidgetArea(w.findChild(QDockWidget))==Qt.RightDockWidgetArea
    assert w.view.port_items[source].brush().color().name()=='#ffffff'
    w.view.wires[line.id].setSelected(True); w.delete_lines()
    assert not p.is_complete(a.id) and not p.is_complete(b.id)
    assert w.view.port_items[source].brush().color().name()=='#fff1d7'
    w.undo(); assert w.project.is_complete(a.id)
    w.save_to(tmp_path/'state.json')
    reopened=Project.load(tmp_path/'state.json')
    assert reopened.is_complete(a.id)
    w.history.mark_saved(w.project); w.close()
    wizard=NodeWizard(); wizard.name.setText('Optional valve'); wizard.prefix.setText('OV')
    assert wizard.ports.cellWidget(0,5).currentText()=='Required'
    wizard.ports.cellWidget(1,5).setCurrentText('Optional'); wizard.submit()
    assert wizard.result()==QDialog.Accepted
    assert [port.required for port in wizard.definition.ports]==[True,False]
    library=ComponentLibrary(tmp_path/'new-library'); library.save(wizard.definition)
    assert ComponentLibrary(tmp_path/'new-library').definitions[wizard.definition.id].ports[1].required is False


def click_scene(w,point,button=Qt.LeftButton):
    QTest.mouseClick(w.view.viewport(),button,pos=w.view.mapFromScene(QPointF(*point)))


def test_live_manual_drawing_cancel_edit_save_undo_and_locked_endpoints(qapp,tmp_path):
    p,a,b,source,target=make_pair(tmp_path)
    w=MainWindow(tmp_path/'library'); w.project=p; w.history=ProjectHistory(p); w.sync_project()
    w.show(); qapp.processEvents(); w.view.fit_content(); w.activateWindow(); w.view.setFocus(); qapp.processEvents()
    click_scene(w,endpoint(p,source)[0]); qapp.processEvents()
    assert w.view.pending_node==source and w.view.preview_item is not None
    QTest.mouseMove(w.view.viewport(),w.view.mapFromScene(QPointF(-80,-20))); qapp.processEvents()
    assert w.view.preview_item.path().elementCount()>=2
    for point in [(-80,-80),(-80,40),(80,40),(80,160)]:
        click_scene(w,point); qapp.processEvents()
    controls=copy.deepcopy(w.view.draft_controls)
    assert len(controls)==4
    for actual,expected in zip(controls,[[-80,-80],[-80,40],[80,40],[80,160]]):
        assert actual==pytest.approx(expected,abs=1)
    click_scene(w,endpoint(p,target)[0]); qapp.processEvents()
    assert w.view.pending_node is None and w.view.preview_item is None and len(p.connections)==1
    line=next(iter(p.connections.values())); graph_before=export_graph(p); identity=logical(line)
    assert line.schematic_geometry['controls']==controls
    original=copy.deepcopy(line.schematic_geometry)
    item=w.view.wires[line.id]; item.setSelected(True); qapp.processEvents()
    assert item.handles
    handle=next(h for h in item.handles if h.kind=='segment' and abs(h.pos().y()-40)<1)
    start=w.view.mapFromScene(handle.scenePos()); end=start+QPoint(0,35)
    QTest.mousePress(w.view.viewport(),Qt.LeftButton,pos=start)
    QTest.mouseMove(w.view.viewport(),end,delay=20)
    QTest.mouseRelease(w.view.viewport(),Qt.LeftButton,pos=end); qapp.processEvents()
    assert line.schematic_geometry!=original
    assert logical(line)==identity and export_graph(p)==graph_before
    edited=copy.deepcopy(line.schematic_geometry)
    assert edited['points'][0]==list(endpoint(p,source)[0])
    assert edited['points'][-1]==list(endpoint(p,target)[0])
    w.undo(); assert w.project.connections[line.id].schematic_geometry==original
    w.redo(); assert w.project.connections[line.id].schematic_geometry==edited
    # Bend dragging also remains a geometry-only edit.
    item=w.view.wires[line.id]; item.setSelected(True); qapp.processEvents()
    handle=next(h for h in item.handles if h.kind=='bend')
    start=w.view.mapFromScene(handle.scenePos()); end=start+QPoint(15,20)
    before_bend=copy.deepcopy(w.project.connections[line.id].schematic_geometry)
    QTest.mousePress(w.view.viewport(),Qt.LeftButton,pos=start)
    QTest.mouseMove(w.view.viewport(),end,delay=20)
    QTest.mouseRelease(w.view.viewport(),Qt.LeftButton,pos=end); qapp.processEvents()
    assert w.project.connections[line.id].schematic_geometry!=before_bend
    assert export_graph(w.project)==graph_before
    w.save_to(tmp_path/'manual.json'); expected=w.project.to_dict(); w.close()
    reopened=MainWindow(tmp_path/'library'); reopened.load_path(tmp_path/'manual.json'); reopened.show(); qapp.processEvents()
    assert reopened.project.to_dict()==expected
    reopened.view.rebuild(); assert reopened.project.to_dict()==expected
    # Start another line on an optional free port; cancellation creates no graph object.
    free=reopened.project.node_for(a.id,'OPTIONAL').id
    before=reopened.project.to_dict(); reopened.view.port_clicked(free)
    QTest.keyClick(reopened.view,Qt.Key_Escape); assert reopened.view.pending_node is None
    reopened.view.port_clicked(free); click_scene(reopened,(0,-200),Qt.RightButton)
    assert reopened.view.pending_node is None and reopened.project.to_dict()==before
    reopened.close()


@pytest.mark.parametrize('degrees',[0,90,180,270,360])
def test_manual_controls_survive_movement_and_rotation(tmp_path,degrees):
    p,a,b,source,target=make_pair(tmp_path)
    controls=[[-80,-80],[-80,40],[80,40],[80,160]]
    c=p.connect(source,target,controls); before=logical(c)
    a.x-=40; a.y-=20; p.rotate(a.id,degrees); p.update_geometry()
    assert c.schematic_geometry['controls']==controls and logical(c)==before
    points=c.schematic_geometry['points']
    for node,tip,lead in [(source,points[0],points[1]),(target,points[-1],points[-2])]:
        location,side=endpoint(p,node); vx,vy=SIDE_VECTORS[side]
        assert tip==list(location)
        assert [lead[0]-tip[0],lead[1]-tip[1]]==[vx*LEAD_LENGTH,vy*LEAD_LENGTH]
    assert normalize(points)==points
    p.save(tmp_path/'moved.json'); assert Project.load(tmp_path/'moved.json').to_dict()==p.to_dict()


def test_crossings_are_render_only_deterministic_and_survive_sample_reopen(qapp,tmp_path):
    sample=ROOT/'examples/c1_r.amcad.json'
    p=Project.load(sample); before=export_graph(p); objects=(len(p.nodes),len(p.connections),len(p.instances))
    lines={c.id:c.schematic_geometry['points'] for c in p.connections.values()}
    crossings=crossing_points(lines)
    assert any(crossings.values())
    assert crossings==crossing_points(dict(reversed(list(lines.items()))))
    w=MainWindow(tmp_path/'library'); w.load_path(sample); w.show(); qapp.processEvents()
    curved=[item for item in w.view.wires.values() if item.crossings]
    assert curved and any(item.path().elementAt(i).isCurveTo() for item in curved for i in range(item.path().elementCount()))
    assert export_graph(w.project)==before
    assert (len(w.project.nodes),len(w.project.connections),len(w.project.instances))==objects
    # No clicking an existing line can insert a junction or split connectivity.
    line=curved[0]; point=line.connection.schematic_geometry['points'][2]
    click_scene(w,point); qapp.processEvents()
    assert export_graph(w.project)==before
    w.grab().save('/tmp/amcad-v12.png')
    w.save_to(tmp_path/'sample.json'); expected=w.project.to_dict(); w.close()
    reopen=MainWindow(tmp_path/'library'); reopen.load_path(tmp_path/'sample.json')
    assert reopen.project.to_dict()==expected
    assert any(item.crossings for item in reopen.view.wires.values())
    reopen.close()


def terminal_nets(graph):
    parent={n['id']:n['id'] for n in graph['nodes']}
    def find(v):
        while parent[v]!=v: v=parent[v]
        return v
    for edge in graph['routing_connections']+[r for r in graph['component_internal_relationships'] if r['relationship']=='JUNCTION']:
        parent[find(edge['from_node_id'])]=find(edge['to_node_id'])
    groups={}
    for n in graph['nodes']:
        if n['kind']!='junction': groups.setdefault(find(n['id']),set()).add(n['label'])
    return {frozenset(labels) for labels in groups.values()}


def test_sample_net_topology_and_legacy_migration_required_defaults(tmp_path):
    fixture=ROOT/'tests/fixtures/c1_r.v1.json'; raw=json.loads(fixture.read_text())
    p=Project.from_dict(raw); p.validate()
    assert p.to_dict()==Project.from_dict(raw).to_dict()
    assert all(port.required for d in p.definitions.values() for port in d.ports)
    expected={frozenset(['C1','EHSV1.C1','RV1.IN']),frozenset(['R','EHSV1.R','RV1.OUT']),
              frozenset(['EHSV1.P']),frozenset(['EHSV1.C2'])}
    assert terminal_nets(export_graph(p))==expected
    current=Project.load(ROOT/'examples/c1_r.amcad.json')
    assert terminal_nets(export_graph(current))==expected
    assert all(current.is_complete(i.id) for i in current.instances.values())
    assert export_graph(current)==json.loads((ROOT/'examples/c1_r.graph.json').read_text())
    assert all(sum(n.id in (c.from_node_id,c.to_node_id) for c in p.connections.values())<=1 for n in p.nodes.values())


@pytest.mark.parametrize('branches',[2,3,4,5,6])
def test_v11_implicit_branch_migration_preserves_nets(tmp_path,branches):
    p=Project(); library=ComponentLibrary(tmp_path/'library')
    root=p.add_instance(library.definitions['external-port'],name='Root')
    peers=[p.add_instance(library.definitions['external-port'],name=f'Peer{i}') for i in range(branches)]
    raw=p.to_dict(); raw['schema_version']=2
    node=p.node_for(root.id,'port')
    for peer in peers:
        target=p.node_for(peer.id,'port')
        raw['connections'].append({'id':new_id(),'from_node_id':node.id,'to_node_id':target.id,
            'from_component_instance_id':node.instance_id,'from_port_id':'port',
            'to_component_instance_id':target.instance_id,'to_port_id':'port'})
    upgraded=Project.from_dict(raw)
    assert terminal_nets(export_graph(upgraded))=={frozenset(['Root',*[f'Peer{i}' for i in range(branches)]])}
    upgraded.validate()
    assert all(len(d.ports) in (3,4) for d in upgraded.definitions.values() if d.symbol.get('kind')=='junction')
    assert upgraded.to_dict()==Project.from_dict(raw).to_dict()


@pytest.mark.parametrize('corruption',['diagonal','nonfinite','endpoint','required','capacity'])
def test_v12_invalid_file_is_rejected(tmp_path,corruption):
    p,a,b,source,target=make_pair(tmp_path); c=p.connect(source,target,[[-80,-80],[-80,160]])
    data=p.to_dict()
    if corruption=='diagonal': data['connections'][0]['schematic_geometry']['points'][2]=[123,456]
    if corruption=='nonfinite': data['connections'][0]['schematic_geometry']['controls'][0][0]=float('nan')
    if corruption=='endpoint': data['connections'][0]['schematic_geometry']['points'][0][0]-=100
    if corruption=='required': data['component_definitions'][0]['ports'][0]['required']='yes'
    if corruption=='capacity':
        other=p.add_instance(p.definitions[b.definition_id],400,200)
        d=p.to_dict(); edge=copy.deepcopy(d['connections'][0]); edge['id']=new_id()
        edge['to_node_id']=p.node_for(other.id,'IN').id; edge['to_component_instance_id']=other.id
        d['connections'].append(edge); data=d
    with pytest.raises(ValueError): Project.from_dict(data)


@pytest.mark.parametrize('side',SIDE_VECTORS)
def test_live_preview_respects_every_source_side(qapp,tmp_path,side):
    p,a,b,source,target=make_pair(tmp_path)
    p.definitions[a.definition_id].ports[0].side=side
    w=MainWindow(tmp_path/'library'); w.project=p; w.history=ProjectHistory(p); w.sync_project()
    w.show(); qapp.processEvents(); w.view.fit_content()
    w.view.port_clicked(source)
    start,_=endpoint(p,source); vx,vy=SIDE_VECTORS[side]
    pos=QPointF(start[0]+vx*100,start[1]+vy*100)
    QTest.mouseMove(w.view.viewport(),w.view.mapFromScene(pos)); qapp.processEvents()
    path=w.view.preview_item.path()
    first,second=path.elementAt(0),path.elementAt(1)
    assert (second.x-first.x,second.y-first.y)==pytest.approx((vx*20,vy*20))
    click_scene(w,(pos.x(),pos.y())); qapp.processEvents()
    assert len(w.view.draft_controls)==1
    w.view.port_clicked(target)
    line=next(iter(p.connections.values()))
    assert line.schematic_geometry['controls']
    assert line.schematic_geometry['points'][0]==list(start)
    w.save_to(tmp_path/'preview.json'); w.close()


def test_vertical_segment_drag_and_translated_copy(qapp,tmp_path):
    p,a,b,source,target=make_pair(tmp_path)
    c=p.connect(source,target,[[-80,-80],[-80,40],[80,40],[80,160]])
    w=MainWindow(tmp_path/'library'); w.project=p; w.history=ProjectHistory(p); w.sync_project()
    w.show(); qapp.processEvents(); w.view.fit_content(); w.activateWindow(); w.view.setFocus(); qapp.processEvents()
    item=w.view.wires[c.id]; item.setSelected(True)
    handle=next(h for h in item.handles if h.kind=='segment'
                and item.connection.schematic_geometry['points'][h.index][0]==item.connection.schematic_geometry['points'][h.index+1][0]
                and h.pos().x()==-80)
    before=copy.deepcopy(c.schematic_geometry); connectivity=export_graph(p)
    start=w.view.mapFromScene(handle.scenePos()); finish=start+QPoint(30,0)
    QTest.mousePress(w.view.viewport(),Qt.LeftButton,pos=start)
    QTest.mouseMove(w.view.viewport(),finish,delay=20)
    QTest.mouseRelease(w.view.viewport(),Qt.LeftButton,pos=finish); qapp.processEvents()
    assert c.schematic_geometry!=before and export_graph(p)==connectivity
    updated=copy.deepcopy(c.schematic_geometry)
    pasted=p.paste_subgraph(p.copy_subgraph([a.id,b.id]),offset=60)
    pasted_line=next(line for line in p.connections.values() if line.from_component_instance_id in pasted)
    assert pasted_line.schematic_geometry['points']==[[x+60,y+60] for x,y in updated['points']]
    assert pasted_line.id!=c.id and pasted_line.from_node_id!=c.from_node_id
    w.sync_project(); w.history.mark_saved(p); w.close()


def test_short_straight_line_is_still_editable(qapp,tmp_path):
    p,a,b,source,target=make_pair(tmp_path)
    b.x=a.x+150; b.y=a.y
    c=p.connect(source,target)
    assert len(c.schematic_geometry['points'])==3
    w=MainWindow(tmp_path/'library'); w.project=p; w.history=ProjectHistory(p); w.sync_project()
    w.show(); qapp.processEvents(); w.view.fit_content()
    item=w.view.wires[c.id]; item.setSelected(True)
    assert item.handles and item.handles[0].kind=='bend'
    handle=item.handles[0]; original=copy.deepcopy(c.schematic_geometry); identity=logical(c)
    start=w.view.mapFromScene(handle.scenePos()); end=start+QPoint(0,30)
    QTest.mousePress(w.view.viewport(),Qt.LeftButton,pos=start)
    QTest.mouseMove(w.view.viewport(),end,delay=20)
    QTest.mouseRelease(w.view.viewport(),Qt.LeftButton,pos=end); qapp.processEvents()
    assert c.schematic_geometry!=original and logical(c)==identity
    assert c.schematic_geometry['points'][0]==list(endpoint(p,source)[0])
    assert c.schematic_geometry['points'][-1]==list(endpoint(p,target)[0])
    w.history.mark_saved(p); w.close()
