from pathlib import Path
from core.project import Project
from core.library import ComponentLibrary
from core.component_definition import ComponentDefinition
from core.port import PortDefinition
from core.graph import save_graph


def create_demo():
    p = Project('C1–R hydraulic architecture')
    library = ComponentLibrary(Path('/tmp/amcad-empty-demo-library'))
    ehsv = ComponentDefinition('demo-ehsv', 'EHSV', 'EHSV', 'Valves', [
        PortDefinition('P', 'P', side='TOP', required=False), PortDefinition('R', 'R', side='BOTTOM'),
        PortDefinition('C1', 'C1', side='LEFT'), PortDefinition('C2', 'C2', side='RIGHT', required=False)])
    rv = ComponentDefinition('demo-relief', 'Relief Valve', 'RV', 'Valves', [
        PortDefinition('IN', 'IN', flow_direction='IN', side='LEFT'),
        PortDefinition('OUT', 'OUT', flow_direction='OUT', side='RIGHT')],
        internal_relationships=[{'from_port_id':'IN', 'to_port_id':'OUT', 'relationship':'RELIEF_VALVE'}])
    c1 = p.add_instance(library.definitions['external-port'], -360, -80, 'C1')
    ret = p.add_instance(library.definitions['external-port'], 420, 160, 'R')
    e = p.add_instance(ehsv, 0, -100, 'EHSV1')
    r = p.add_instance(rv, 0, 160, 'RV1')
    j = p.add_instance(library.definitions['junction-3'], -200, -80, 'J1')
    ret.rotation = 180
    j2 = p.add_instance(library.definitions['junction-3'], 240, 160, 'J2')
    j2.rotation = 180
    for a, ap, b, bp in [(c1,'port',j,'LEFT'),(j,'RIGHT',e,'C1'),(j,'BOTTOM',r,'IN'),(r,'OUT',j2,'RIGHT'),(e,'R',j2,'BOTTOM'),(j2,'LEFT',ret,'port')]:
        p.connect(p.node_for(a.id,ap).id, p.node_for(b.id,bp).id)
    controls = [[], [[-120,-80],[-120,-100]],
                [[-200,240],[120,240],[120,100],[-100,100],[-100,160]],
                [[150,160]], [[0,300],[300,300],[300,80],[240,80],[240,120]], [[320,160]]]
    for connection, points in zip(p.connections.values(),controls):
        p.set_line_geometry(connection.id,points)
    return p


if __name__ == '__main__':
    root = Path(__file__).parent
    project = create_demo()
    project.save(root / 'c1_r.amcad.json')
    save_graph(project, root / 'c1_r.graph.json')
