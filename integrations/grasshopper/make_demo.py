"""Regenerate only the isolated integration demo; never accesses a user library."""
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL
from core.project import Project,write_json
from core.generic import generic_component
from core.library import ComponentLibrary
from core.cavity import CavityProfile,ProfileVertex,Corner,HydraulicInterface
from core.cavity_definition import CavityDefinition
from core.cavity_surface import SurfaceAnchor,ChannelSection
from core.grasshopper_export import save_grasshopper
from integrations.grasshopper.amcad_runtime import pose


def stable(name):return str(uuid5(NAMESPACE_URL,'amcad-grasshopper-demo:'+name))


def demo_project():
    project=Project('Grasshopper Phase 1 shared cavity demo');project.metadata['id']=stable('project')
    profile=CavityProfile([ProfileVertex(z,r,id=stable('vertex:'+str(index))) for index,(z,r) in enumerate([(0,0),(0,4),(6,4),(6,3),(12,3),(12,0)])],id=stable('profile'))
    profile.set_corner(profile.vertices[1].id,Corner('FILLET',radius_mm=.5))
    profile.set_corner(profile.vertices[3].id,Corner('CHAMFER',length_mm=.5,angle_deg=30))
    markers=[]
    for index,(segment,angle) in enumerate([(1,0),(3,180)]):
        uid=stable('interface:'+str(index))
        markers.append(HydraulicInterface(uid,'SURFACE',id=uid,surface_anchor=SurfaceAnchor('LINE',profile.vertices[segment].id,profile.vertices[segment+1].id,t=.5,angle_deg=angle),
            section=ChannelSection('CIRCLE',diameter_mm=2) if index==0 else ChannelSection('SLOT',width_mm=1.5,length_mm=3),section_rotation_deg=20 if index else 0))
    cavity=CavityDefinition('Demo stepped check cavity',profile,markers,id=stable('cavity')).validate()
    definition=generic_component(2);definition.id=stable('component');definition.name='Demo Check Valve'
    # Only built-in templates are read. The isolated directory is not created or written.
    builtins=ComponentLibrary(Path(__file__).parent/'nonexistent-demo-library').definitions
    instances=[]
    for name,d in [('CV1',definition),('CV2',definition),('J1',builtins['junction-3']),('Boundary',builtins['external-port'])]:
        instance=project.add_instance(d,x=1000+len(instances)*333,y=-800, name=name)
        old=instance.id;instance.id=stable('instance:'+name);del project.instances[old];project.instances[instance.id]=instance
        for node in list(project.nodes.values()):
            if node.instance_id==old:
                del project.nodes[node.id];node.instance_id=instance.id;node.id=stable('node:'+name+':'+node.port_id);project.nodes[node.id]=node
        instances.append(instance)
    a,b,j,boundary=instances
    for instance in (a,b):project.assign_cavity(instance.id,cavity,{'p1':markers[0].id,'p2':markers[1].id})
    sides={p.side:p.id for p in builtins['junction-3'].ports}
    for index,(instance,pid,side) in enumerate([(a,'p1','LEFT'),(b,'p2','RIGHT'),(boundary,'port','BOTTOM')]):
        connection=project.connect(project.node_for(instance.id,pid).id,project.node_for(j.id,sides[side]).id)
        old=connection.id;connection.id=stable('edge:'+str(index));del project.connections[old];project.connections[connection.id]=connection
    return project.validate()


if __name__=='__main__':
    folder=Path(__file__).parent;project=demo_project();project.save(folder/'demo_project.amcad.json');save_grasshopper(project,folder/'demo.grasshopper.json')
    write_json(folder/'demo.placements.json',{'schema':'amcad.placements','schema_version':1,'units':'mm','project_id':project.metadata['id'],
        'placements':{stable('instance:CV1'):pose(),stable('instance:CV2'):pose([30,10,5],[15,30,90])}})
