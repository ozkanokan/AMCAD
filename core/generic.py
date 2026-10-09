"""Configurable generic symbols retain surviving logical port IDs."""
from copy import deepcopy
from core.component_definition import ComponentDefinition
from core.port import PortDefinition, new_id


def generic_component(count):
    if not isinstance(count,int) or isinstance(count,bool) or not 1 <= count <= 128:
        raise ValueError('Generic port count must be between 1 and 128')
    ports=[PortDefinition(f'p{i+1}',f'Port {i+1}',side='LEFT' if i<count/2 else 'RIGHT') for i in range(count)]
    return ComponentDefinition(new_id(),'N-Port Generic','G','Generic',ports,
        symbol={'kind':'box','width':110,'height':76,'configurable_ports':True}).validate()


def resized_generic(original,count):
    generic_component(count)  # Validate the requested range before changing anything.
    result=deepcopy(original);result.id=new_id();result.revision=1
    result.default_cavity_ref=None;result.default_port_mapping={}
    result.ports=deepcopy(original.ports[:count])
    used={p.id for p in result.ports}
    for index in range(len(result.ports),count):
        pid=f'p{index+1}'
        while pid in used:pid+='_'
        used.add(pid);result.ports.append(PortDefinition(pid,f'Port {index+1}',side='RIGHT'))
    return result.validate()
