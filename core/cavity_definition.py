"""Independent reusable cavity data, separate from schematic definitions."""
from copy import deepcopy
from dataclasses import dataclass,field,asdict
from uuid import UUID,uuid5
import hashlib
import json
from core.port import new_id,PortDefinition
from core.cavity import CavityProfile,HydraulicInterface,PhysicalDefinition
from core.cavity_surface import resolve_anchor,legacy_surface_anchor


@dataclass
class CavityDefinition:
    name: str
    profile: CavityProfile
    interfaces: list[HydraulicInterface]=field(default_factory=list)
    id: str=field(default_factory=new_id)
    revision: int=1
    geometry_type: str='REVOLVED_PROFILE'
    description: str=''

    @property
    def port_count(self): return len(self.interfaces)

    def physical(self):
        return PhysicalDefinition(self.geometry_type,self.profile,self.interfaces)

    def editor_ports(self):
        return [PortDefinition(m.id,f'Interface {index+1}',required=False) for index,m in enumerate(self.interfaces)]

    def validate(self,strict=True):
        if not isinstance(self.id,str) or not self.id: raise ValueError('Cavity needs a persistent ID')
        if not isinstance(self.name,str) or not self.name.strip(): raise ValueError('Cavity name is required')
        if type(self.revision)!=int or self.revision<1: raise ValueError('Cavity revision must be a positive integer')
        if not isinstance(self.description,str): raise ValueError('Cavity description must be text')
        if self.geometry_type!='REVOLVED_PROFILE' or self.profile is None: raise ValueError('Cavity requires revolved profile geometry')
        if any(m.hydraulic_port_id!=m.id for m in self.interfaces): raise ValueError('Independent interface identity must equal its own persistent ID')
        self.physical().validate(self.editor_ports(),strict=strict)
        if strict:
            for m in self.interfaces:
                if m.surface_anchor is None: raise ValueError('Cavity interface needs a valid surface anchor; reattach legacy interfaces explicitly')
                resolve_anchor(self.profile,m.surface_anchor)
        return self

    def to_dict(self):
        data={'schema':'amcad.cavity','schema_version':1,**asdict(self),'port_count':self.port_count}
        for m in data['interfaces']:
            if m['direction'] is not None:m['direction']=list(m['direction'])
        return data

    @classmethod
    def from_dict(cls,data):
        data=deepcopy(data)
        if data.pop('schema',None)!='amcad.cavity' or data.pop('schema_version',None)!=1: raise ValueError('Unsupported cavity schema/version')
        count=data.pop('port_count',None)
        data['profile']=CavityProfile.from_dict(data['profile'])
        data['interfaces']=[HydraulicInterface.from_dict(m) for m in data.get('interfaces',[])]
        result=cls(**data).validate(strict=False)
        if count is not None and (type(count)!=int or count!=result.port_count): raise ValueError('Cavity port count disagrees with interfaces')
        return result

    def duplicate(self,name=None):
        result=deepcopy(self);result.id=new_id();result.name=name or self.name+' (Copy)';result.revision=1
        result.profile.id=new_id()
        vertex_ids={v.id:new_id() for v in result.profile.vertices}
        for v in result.profile.vertices:v.id=vertex_ids[v.id]
        for m in result.interfaces:
            m.id=new_id();m.hydraulic_port_id=m.id
            if m.surface_anchor:
                a=m.surface_anchor
                # Invalid references remain invalid, never reassigned by duplication.
                a.vertex_id=vertex_ids.get(a.vertex_id,a.vertex_id)
                a.next_vertex_id=vertex_ids.get(a.next_vertex_id,a.next_vertex_id)
        return result


def legacy_cavity(project,instance_id):
    """Explicit per-instance import, content-addressed and repeatable; no shared guesses."""
    instance=project.instances[instance_id];definition=project.definitions[instance.definition_id]
    physical=deepcopy(definition.physical)
    if physical.cavity_type=='NONE': raise ValueError('This component has no legacy embedded cavity')
    digest=hashlib.sha256(json.dumps(asdict(physical),sort_keys=True,allow_nan=False).encode()).hexdigest()
    namespace=UUID('8c680b0a-3c5f-4a78-b7ad-974b4039656a')
    cavity_id=str(uuid5(namespace,project.metadata['id']+':'+instance.id+':'+digest))
    mapping={}
    for m in physical.hydraulic_interfaces:
        port=m.hydraulic_port_id
        m.id=str(uuid5(UUID(cavity_id),m.id));m.hydraulic_port_id=m.id;mapping[port]=m.id
        if m.surface_anchor is None:
            m.surface_anchor=deepcopy(legacy_surface_anchor(physical.cavity_profile,m))
    cavity=CavityDefinition(instance.name+' cavity',physical.cavity_profile,physical.hydraulic_interfaces,id=cavity_id)
    return cavity.validate(strict=False),mapping
