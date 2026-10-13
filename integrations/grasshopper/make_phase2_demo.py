"""Isolated seven-instance placement demo; does not rewrite Phase 1 assets."""
from pathlib import Path
from copy import deepcopy
from core.project import write_json
from core.grasshopper_export import export_grasshopper
from integrations.grasshopper.make_demo import demo_project,stable
from integrations.grasshopper.amcad_runtime import pose


def project_with_instances(count=7):
    if count<2:raise ValueError('Demo needs at least two instances')
    project=demo_project();project.metadata={'id':stable('phase2-project'),'name':'Phase 2 placement controller · '+str(count)+' cavities'}
    definition=project.definitions[project.instances[stable('instance:CV1')].definition_id]
    cavity=next(iter(project.cavities.values()));mapping=project.instances[stable('instance:CV1')].port_mapping
    for index in range(3,count+1):
        name='CV'+str(index);instance=project.add_instance(definition,333*index,-700,name=name)
        old=instance.id;instance.id=stable('instance:'+name);del project.instances[old];project.instances[instance.id]=instance
        for node in list(project.nodes.values()):
            if node.instance_id==old:
                del project.nodes[node.id];node.instance_id=instance.id;node.id=stable('node:'+name+':'+node.port_id);project.nodes[node.id]=node
        project.assign_cavity(instance.id,cavity,deepcopy(mapping))
    return project.validate()


if __name__=='__main__':
    folder=Path(__file__).resolve().parent;project=project_with_instances();data=export_grasshopper(project)
    write_json(folder/'phase2-seven.grasshopper.json',data)
    write_json(folder/'phase2-seven.placements.json',{'schema':'amcad.placements','schema_version':1,'units':'mm','project_id':project.metadata['id'],
        'placements':{stable('instance:CV'+str(i)):pose([(i-1)*25,0,0]) for i in range(1,8)}})
