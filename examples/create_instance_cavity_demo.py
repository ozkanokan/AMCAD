"""Portable V1.5 example: connected instances of one symbol with independent cavities."""
from pathlib import Path
from copy import deepcopy
from core.project import Project
from core.library import ComponentLibrary
from core.cavity_definition import CavityDefinition
from core.port import new_id
from core.graph import save_graph


def create_instance_cavity_demo():
    root=Path(__file__).parent
    source=Project.load(root/'parallel_check_valves_v14a.amcad.json')
    physical=source.definitions['illustrative-check-valve'].physical
    marker=deepcopy(physical.hydraulic_interfaces[0]);marker.id=new_id();marker.hydraulic_port_id=marker.id
    first=CavityDefinition('CAVITY_A',deepcopy(physical.cavity_profile),[marker],description='Independent one-interface engineering example')
    second=first.duplicate('CAVITY_B');second.profile.vertices[-1].z=30
    project=Project('Independent R and RET cavity assignment')
    component=ComponentLibrary(root/'unused-components').definitions['external-port']
    a=project.add_instance(component,0,0,'R');b=project.add_instance(component,300,0,'RET')
    port_id=component.ports[0].id
    project.connect(project.node_for(a.id,port_id).id,project.node_for(b.id,port_id).id)
    project.assign_cavity(a.id,first,{port_id:first.interfaces[0].id})
    project.assign_cavity(b.id,second,{port_id:second.interfaces[0].id})
    return project.validate()


if __name__=='__main__':
    root=Path(__file__).parent;project=create_instance_cavity_demo()
    project.save(root/'instance_cavities.amcad.json');save_graph(project,root/'instance_cavities.graph.json')
