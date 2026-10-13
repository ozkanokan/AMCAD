"""Separate physical handoff. Schematic positions/rotation never cross this boundary."""
from copy import deepcopy
from dataclasses import asdict
from uuid import uuid5,NAMESPACE_URL
from core.project import write_json
from core.cavity_surface import interface_pose,section_frame,ChannelSection,surface_patches


def export_grasshopper(project):
    # Validate a copy: legacy interface normalization must never mutate the project.
    project=deepcopy(project);project.validate()
    instances=[];cavities={};excluded=[]
    for instance in project.instances.values():
        if not instance.cavity_ref:
            excluded.append({'instance_id':instance.id,'name':instance.name,'reason':'No independent cavity assignment'})
            continue
        cavity=project.cavities[instance.cavity_ref];cavity.validate()
        project.validate_assignment(instance,cavity,instance.port_mapping)
        if cavity.id not in cavities:
            interfaces=[]
            for index,interface in enumerate(cavity.interfaces):
                position,direction=interface_pose(cavity.profile,interface)
                u,v=section_frame(direction,interface.section_rotation_deg)
                section=interface.section or ChannelSection(diameter_mm=interface.nominal_connection_diameter_mm)
                interfaces.append({'id':interface.id,'label':f'Interface {index+1}',
                    'source':asdict(interface),'position_mm':position,'direction':direction,
                    'section':asdict(section),'section_u':u,'section_v':v})
            # Use AMCAD's evaluated features, including endpoint treatments and true arcs.
            segments=[]
            for patch in surface_patches(cavity.profile):
                feature=deepcopy(patch.feature)
                if feature['kind']=='arc':feature['start']=feature['entry'];feature['end']=feature['exit']
                feature['anchor']=asdict(patch.anchor);segments.append(feature)
            cavities[cavity.id]={'id':cavity.id,'name':cavity.name,'revision':cavity.revision,
                'geometry_type':cavity.geometry_type,'profile':cavity.profile.to_dict(),
                'segments':segments,'interfaces':interfaces}
        instances.append({'id':instance.id,'name':instance.name,'cavity_id':cavity.id,
            'cavity_revision':cavity.revision,'port_mapping':dict(instance.port_mapping)})
    physical={i['id']:i for i in instances}
    def terminal(node):
        instance=physical.get(node.instance_id)
        return {'instance_id':node.instance_id,'interface_id':instance['port_mapping'][node.port_id]} if instance else None
    nodes=[]
    for node in project.nodes.values():
        port=next(p for p in project.effective_definition(node.instance_id).ports if p.id==node.port_id)
        nodes.append({'id':node.id,'instance_id':node.instance_id,'port_id':node.port_id,
                      'name':project.instances[node.instance_id].name+'.'+port.display_name,
                      'kind':node.kind,'physical_terminal':terminal(node)})
    edges=[{'id':c.id,'from_node_id':c.from_node_id,'to_node_id':c.to_node_id,
            'from_terminal':terminal(project.nodes[c.from_node_id]),'to_terminal':terminal(project.nodes[c.to_node_id])}
           for c in project.connections.values()]
    relationships=[]
    for instance in project.instances.values():
        for r in project.definitions[instance.definition_id].internal_relationships:
            relationships.append({'instance_id':instance.id,'from_node_id':project.node_for(instance.id,r['from_port_id']).id,
                'to_node_id':project.node_for(instance.id,r['to_port_id']).id,'relationship':r.get('relationship','UNSPECIFIED')})
    parent={n['id']:n['id'] for n in nodes}
    def find(key):
        while parent[key]!=key:key=parent[key]
        return key
    for edge in edges+[r for r in relationships if r['relationship']=='JUNCTION']:
        parent[find(edge['from_node_id'])]=find(edge['to_node_id'])
    groups={}
    for node in nodes:groups.setdefault(find(node['id']),[]).append(node)
    nets=[]
    for members in groups.values():
        ids=sorted(n['id'] for n in members)
        nets.append({'id':str(uuid5(NAMESPACE_URL,'amcad-net:'+project.metadata['id']+':'+','.join(ids))),
            'node_ids':ids,'terminals':[n['physical_terminal'] for n in members if n['physical_terminal']],
            'boundary_node_ids':[n['id'] for n in members if not n['physical_terminal'] and n['kind']!='junction']})
    result={'schema':'amcad.grasshopper','schema_version':1,'units':'mm','project':dict(project.metadata),
        'coordinate_system':{'handedness':'RIGHT','revolve_axis':'LOCAL_Z','profile_coordinates':['axial_z','radial_y'],
                             'profile_embedding_xyz':['radial_y',0,'axial_z'],'placement_source':'GRASSHOPPER_ONLY'},
        'instances':instances,'cavities':list(cavities.values()),'excluded_instances':excluded,
        'connectivity':{'nodes':nodes,'edges':edges,'internal_relationships':relationships,'nets':nets}}
    # JSON-normalize tuples; exporter and consumer share the same strict contract.
    import json
    result=json.loads(json.dumps(result,allow_nan=False))
    from integrations.grasshopper.amcad_runtime import validate_export
    validate_export(result)
    return result


def save_grasshopper(project,path):
    from pathlib import Path
    import json
    path=Path(path)
    if path.exists():
        try:old=json.loads(path.read_text(encoding='utf-8'))
        except (ValueError,OSError) as error:raise ValueError('Choose a new Grasshopper export file') from error
        if not isinstance(old,dict) or old.get('schema')!='amcad.grasshopper':
            raise ValueError('Export cannot overwrite a project, cavity, placement or unrelated file')
    write_json(path,export_grasshopper(project))
