"""Illustrative dimensions only; not a commercial valve cavity standard."""
from pathlib import Path
from core.cavity import CavityProfile,ProfileVertex,Corner,PhysicalDefinition,HydraulicInterface
from core.component_definition import ComponentDefinition
from core.port import PortDefinition
from core.project import Project,write_json
from core.library import ComponentLibrary
from core.graph import save_graph


def check_valve_definition():
    profile=CavityProfile([ProfileVertex(0,7),ProfileVertex(8,7),ProfileVertex(8,5),
                           ProfileVertex(20,5),ProfileVertex(20,3),ProfileVertex(28,3)])
    profile.set_corner(profile.vertices[1].id,Corner('FILLET',radius_mm=.5))
    profile.set_corner(profile.vertices[3].id,Corner('CHAMFER',length_mm=.4,angle_deg=45))
    return ComponentDefinition('illustrative-check-valve','Illustrative Check Valve','CV','Valves',[
        PortDefinition('IN','IN',flow_direction='IN',side='LEFT'),PortDefinition('OUT','OUT',flow_direction='OUT',side='RIGHT')],
        symbol={'kind':'box','width':200,'height':76},
        internal_relationships=[{'from_port_id':'IN','to_port_id':'OUT','relationship':'CHECK_VALVE'}],
        physical=PhysicalDefinition('REVOLVED_PROFILE',profile,[
            HydraulicInterface('IN','AXIAL',28,0,4,'AXIAL_POSITIVE'),
            HydraulicInterface('OUT','RADIAL',14.5,5,4,'RADIAL')])).validate()


def create_physical_demo():
    p=Project('Illustrative parallel Check Valve physical demonstrator')
    library=ComponentLibrary(Path('/tmp/amcad-physical-demo-empty-library'))
    external=library.definitions['external-port']; junction=library.definitions['junction-3']
    valve=check_valve_definition()
    inlet=p.add_instance(external,-340,0,'IN')
    j=p.add_instance(junction,-180,0,'J1')
    cv1=p.add_instance(valve,40,-100,'CV1'); cv2=p.add_instance(valve,40,100,'CV2')
    out1=p.add_instance(external,300,-100,'OUT1'); out2=p.add_instance(external,300,100,'OUT2')
    out1.rotation=180; out2.rotation=180
    routes=[(inlet,'port',j,'LEFT',[]),(j,'RIGHT',cv1,'IN',[[-80,0],[-80,-100]]),
            (j,'BOTTOM',cv2,'IN',[[-180,100],[-80,100]]),(cv1,'OUT',out1,'port',[[180,-100]]),
            (cv2,'OUT',out2,'port',[[180,100]])]
    for a,ap,b,bp,controls in routes:
        p.connect(p.node_for(a.id,ap).id,p.node_for(b.id,bp).id,controls)
    return p


if __name__=='__main__':
    root=Path(__file__).parent
    project=create_physical_demo()
    project.save(root/'parallel_check_valves.amcad.json')
    save_graph(project,root/'parallel_check_valves.graph.json')
    write_json(root/'illustrative_check_valve.component.json',project.definitions['illustrative-check-valve'].to_dict())
