"""Portable Python 3.9+ contract/placement runtime; no AMCAD, Qt or Rhino imports."""
import json
import math
import os
from pathlib import Path
import tempfile
from copy import deepcopy


class ImportErrorDetail(ValueError):
    pass


def require(condition,message):
    if not condition:raise ImportErrorDetail(message)


def number(value,label):
    require(type(value) in (int,float) and math.isfinite(value),label+' must be finite')
    return value


def vector(value,label,size=3):
    require(isinstance(value,(list,tuple)) and len(value)==size,label+' needs '+str(size)+' coordinates')
    return tuple(number(v,label) for v in value)


def unit(value,label):
    value=vector(value,label);require(abs(math.sqrt(sum(v*v for v in value))-1)<1e-8,label+' must be normalized')
    return value


def identifier(value,label):require(isinstance(value,str) and bool(value.strip()),label+' needs a stable ID')
def close(a,b):return len(a)==len(b) and all(abs(x-y)<1e-7 for x,y in zip(a,b))


def indexed(records,label):
    require(isinstance(records,list),label+' must be an array');result={}
    for record in records:
        require(isinstance(record,dict),label+' entries must be objects');identifier(record.get('id'),label)
        require(record['id'] not in result,'Duplicate '+label+' ID: '+record['id']);result[record['id']]=record
    return result


def validate_export(data):
    try:return _validate_export(data)
    except (KeyError,TypeError,AttributeError,IndexError) as error:
        raise ImportErrorDetail('Malformed AMCAD export: '+str(error)) from error


def _validate_export(data):
    require(isinstance(data,dict) and data.get('schema')=='amcad.grasshopper' and type(data.get('schema_version')) is int and data['schema_version']==1,'Unsupported AMCAD Grasshopper schema/version')
    require(data.get('units')=='mm','AMCAD export must use millimeters')
    identifier(data['project']['id'],'Project');identifier(data['project']['name'],'Project name')
    require(data['coordinate_system']=={'handedness':'RIGHT','revolve_axis':'LOCAL_Z','profile_coordinates':['axial_z','radial_y'],'profile_embedding_xyz':['radial_y',0,'axial_z'],'placement_source':'GRASSHOPPER_ONLY'},'Unsupported coordinate convention')
    cavities=indexed(data['cavities'],'cavity');instances=indexed(data['instances'],'instance')
    interfaces={}
    for cavity in cavities.values():
        require(cavity['geometry_type']=='REVOLVED_PROFILE','Unsupported cavity geometry: '+str(cavity['geometry_type']))
        require(type(cavity['revision']) is int and cavity['revision']>=1,'Invalid cavity revision')
        profile=cavity['profile'];require(profile['units']=='mm' and type(profile['schema_version']) is int and profile['schema_version']==1,'Unsupported profile schema/units')
        vertices=indexed(profile['vertices'],'vertex');require(len(vertices)>=3,'A revolved profile needs at least three vertices')
        for vertex in vertices.values():
            number(vertex['z'],'Vertex Z');require(number(vertex['r'],'Vertex Y')>=0,'Vertex Y cannot be negative')
            corner=vertex['corner'];kind=corner['type'];require(kind in ('SHARP','FILLET','CHAMFER'),'Unsupported corner feature')
            if kind=='FILLET':require(number(corner['radius_mm'],'Fillet radius')>0,'Invalid fillet radius')
            if kind=='CHAMFER':require(number(corner['length_mm'],'Chamfer length')>0 and 0<number(corner['angle_deg'],'Chamfer angle')<180,'Invalid chamfer')
            require(not (kind=='FILLET' and (corner.get('length_mm') is not None or corner.get('angle_deg') is not None)) and not (kind=='CHAMFER' and corner.get('radius_mm') is not None) and not (kind=='SHARP' and any(corner.get(f) is not None for f in ('radius_mm','length_mm','angle_deg'))),'Mutually exclusive corner parameters required')
        require(profile['vertices'][0]['r']==0 and profile['vertices'][-1]['r']==0,'Open-axis profiles are unsupported')
        segments=cavity['segments'];require(isinstance(segments,list) and bool(segments),'Missing exact profile segments')
        previous=None;treated=set()
        for segment in segments:
            kind=segment['kind'];require(kind in ('line','arc'),'Unsupported segment geometry')
            start=vector(segment['start'],'Segment start',2);end=vector(segment['end'],'Segment end',2)
            require(min(start[1],end[1])>=-1e-9 and not close(start,end),'Invalid segment endpoints')
            if previous is not None:require(close(previous,start),'Profile segments are discontinuous')
            previous=end;anchor=segment['anchor'];require(anchor['vertex_id'] in vertices,'Unknown segment vertex ID')
            if anchor['kind']=='LINE':require(anchor['next_vertex_id'] in vertices and kind=='line','Invalid line anchor')
            elif anchor['kind'] in ('FILLET','CHAMFER'):
                vertex=vertices[anchor['vertex_id']];require(vertex['corner']['type']==anchor['kind'],'Corner segment does not match theoretical vertex')
                require(anchor['vertex_id'] not in treated,'Duplicate corner segment');treated.add(anchor['vertex_id'])
                require(kind==('arc' if anchor['kind']=='FILLET' else 'line'),'Unsupported corner geometry')
                if anchor['kind']=='CHAMFER':
                    ordered=profile['vertices'];index=next(i for i,v in enumerate(ordered) if v['id']==vertex['id']);previous_vertex=ordered[(index-1)%len(ordered)]
                    incoming=(vertex['z']-previous_vertex['z'],vertex['r']-previous_vertex['r']);chord=(end[0]-start[0],end[1]-start[1])
                    incoming_length=math.hypot(*incoming);chord_length=math.hypot(*chord)
                    require(incoming_length>0 and chord_length>0,'Degenerate chamfer')
                    expected_start=(vertex['z']-incoming[0]/incoming_length*vertex['corner']['length_mm'],vertex['r']-incoming[1]/incoming_length*vertex['corner']['length_mm'])
                    require(close(start,expected_start),'Chamfer setback differs from corner length')
                    angle=math.degrees(math.acos(max(-1,min(1,sum(a*b for a,b in zip(incoming,chord))/incoming_length/chord_length))))
                    require(abs(angle-vertex['corner']['angle_deg'])<1e-7,'Chamfer angle differs from corner parameter')
            else:raise ImportErrorDetail('Unsupported segment anchor')
            if kind=='arc':
                center=vector(segment['center'],'Arc center',2);radius=number(segment['radius'],'Arc radius')
                sweep=number(segment['sweep_deg'],'Arc sweep');angle=number(segment['start_deg'],'Arc angle')
                require(radius>0 and 0<abs(sweep)<180,'Unsupported arc radius/sweep')
                require(abs(radius-vertices[anchor['vertex_id']]['corner']['radius_mm'])<1e-8,'Arc radius differs from corner parameter')
                def arc_point(degrees):
                    a=math.radians(degrees);return (center[0]+radius*math.cos(a),center[1]+radius*math.sin(a))
                require(close(start,arc_point(angle)) and close(end,arc_point(angle+sweep)),'Arc endpoints disagree with its parameters')
                delta=(270-angle)%360 if sweep>0 else (angle-270)%360
                if delta<=abs(sweep):require(center[1]-radius>=-1e-9,'Arc crosses revolve axis')
        require(abs(segments[0]['start'][1])<1e-8 and abs(segments[-1]['end'][1])<1e-8,'Derived profile must end on the revolve axis')
        require(treated=={v['id'] for v in vertices.values() if v['corner']['type']!='SHARP'},'Missing derived corner geometry')
        interfaces[cavity['id']]=indexed(cavity['interfaces'],'interface')
        for interface in interfaces[cavity['id']].values():
            vector(interface['position_mm'],'Interface position');direction=unit(interface['direction'],'Interface direction')
            u=unit(interface['section_u'],'Section U');v=unit(interface['section_v'],'Section V')
            require(abs(sum(a*b for a,b in zip(u,v)))<1e-8 and abs(sum(a*b for a,b in zip(u,direction)))<1e-8 and close((u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]),direction),'Invalid interface section frame')
            section=interface['section'];kind=section['type'];require(kind in ('CIRCLE','SLOT','RECTANGLE'),'Unsupported interface section')
            for field in {'CIRCLE':['diameter_mm'],'SLOT':['width_mm','length_mm'],'RECTANGLE':['width_mm','height_mm']}[kind]:require(number(section[field],'Section size')>0,'Invalid section size')
            if kind=='SLOT':require(section['length_mm']>=section['width_mm'],'Slot length must exceed its width')
            require(interface['source']['id']==interface['id'] and interface['source']['hydraulic_port_id']==interface['id'],'Interface source identity disagrees')
    for instance in instances.values():
        require(not any(key in instance for key in ('x','y','rotation','placement','translation_mm')),'Schematic or placement coordinates must not enter the geometry export')
        require(instance['cavity_id'] in cavities,'Missing cavity reference');cavity=cavities[instance['cavity_id']]
        require(type(instance['cavity_revision']) is int and instance['cavity_revision']==cavity['revision'],'Cavity revision mismatch')
        mapping=instance['port_mapping'];require(isinstance(mapping,dict) and all(isinstance(k,str) and k for k in mapping),'Invalid schematic port mapping')
        values=list(mapping.values());require(all(isinstance(v,str) for v in values) and len(values)==len(set(values)) and set(values)==set(interfaces[cavity['id']]),'Mapping must be complete and one-to-one')
    graph=data['connectivity'];nodes=indexed(graph['nodes'],'connectivity node');edges=indexed(graph['edges'],'connectivity edge');nets=indexed(graph['nets'],'net')
    def terminal(value):
        if value is None:return
        require(value['instance_id'] in instances,'Unknown physical instance in connectivity')
        inst=instances[value['instance_id']];require(value['interface_id'] in interfaces[inst['cavity_id']],'Unknown physical interface in connectivity')
    for node in nodes.values():
        terminal(node['physical_terminal']);inst=instances.get(node['instance_id'])
        expected={'instance_id':inst['id'],'interface_id':inst['port_mapping'].get(node['port_id'])} if inst else None
        require(node['physical_terminal']==expected,'Connectivity terminal disagrees with port mapping')
    for edge in edges.values():
        for side in ('from','to'):
            require(edge[side+'_node_id'] in nodes,'Unknown connection node')
            require(edge[side+'_terminal']==nodes[edge[side+'_node_id']]['physical_terminal'],'Connection terminal disagrees')
    for relation in graph['internal_relationships']:require(relation['from_node_id'] in nodes and relation['to_node_id'] in nodes,'Unknown internal relationship node')
    node_pairs=[(n['instance_id'],n['port_id']) for n in nodes.values()]
    require(len(node_pairs)==len(set(node_pairs)),'Duplicate connectivity port identity')
    for instance in instances.values():
        require({n['port_id'] for n in nodes.values() if n['instance_id']==instance['id']}==set(instance['port_mapping']),'Connectivity omits mapped ports')
    parent={key:key for key in nodes}
    def root(key):
        while parent[key]!=key:key=parent[key]
        return key
    for edge in list(edges.values())+[r for r in graph['internal_relationships'] if r['relationship']=='JUNCTION']:
        parent[root(edge['from_node_id'])]=root(edge['to_node_id'])
    actual_groups={}
    for key in nodes:actual_groups.setdefault(root(key),set()).add(key)
    require({frozenset(net['node_ids']) for net in nets.values()}=={frozenset(group) for group in actual_groups.values()},'Nets disagree with wire/junction topology')
    members=[]
    for net in nets.values():
        require(all(n in nodes for n in net['node_ids']),'Unknown net node');members.extend(net['node_ids'])
        require(set(net['boundary_node_ids'])=={n for n in net['node_ids'] if nodes[n]['physical_terminal'] is None and nodes[n]['kind']!='junction'},'Net boundaries disagree')
        for value in net['terminals']:terminal(value)
        require(net['terminals']==[nodes[n]['physical_terminal'] for n in net['node_ids'] if nodes[n]['physical_terminal']] or sorted((t['instance_id'],t['interface_id']) for t in net['terminals'])==sorted((nodes[n]['physical_terminal']['instance_id'],nodes[n]['physical_terminal']['interface_id']) for n in net['node_ids'] if nodes[n]['physical_terminal']),'Net terminals disagree')
    require(len(members)==len(set(members)) and set(members)==set(nodes),'Nets must partition all connectivity nodes')
    return data


def load_export(path):
    try:
        with open(path,encoding='utf-8') as stream:data=json.load(stream,parse_constant=lambda value:(_ for _ in ()).throw(ImportErrorDetail('Nonfinite JSON number: '+value)))
        return validate_export(data)
    except (OSError,json.JSONDecodeError) as error:raise ImportErrorDetail('Cannot read AMCAD export: '+str(error)) from error


def pose(translation=None,rotation=None):
    return {'translation_mm':list(vector([0,0,0] if translation is None else translation,'Translation')),
            'rotation_deg':list(vector([0,0,0] if rotation is None else rotation,'Rotation'))}


def matrix(placement):
    x,y,z=vector(placement['translation_mm'],'Translation');rx,ry,rz=[math.radians(v) for v in vector(placement['rotation_deg'],'Rotation')]
    a,b,c=math.cos(rx),math.cos(ry),math.cos(rz);s,t,u=math.sin(rx),math.sin(ry),math.sin(rz)
    return [[c*b,c*t*s-u*a,c*t*a+u*s,x],[u*b,u*t*s+c*a,u*t*a-c*s,y],[-t,b*s,b*a,z],[0,0,0,1]]


def transform_point(transform,point):
    point=vector(point,'Point');return tuple(sum(transform[i][j]*point[j] for j in range(3))+transform[i][3] for i in range(3))


def transform_vector(transform,direction):
    direction=vector(direction,'Vector');return tuple(sum(transform[i][j]*direction[j] for j in range(3)) for i in range(3))


def load_placements(path,project_id):
    if not path or not Path(path).exists():return {'schema':'amcad.placements','schema_version':1,'units':'mm','project_id':project_id,'placements':{}}
    try:
        with open(path,encoding='utf-8') as stream:data=json.load(stream)
        require(data['schema']=='amcad.placements' and type(data['schema_version']) is int and data['schema_version']==1 and data['units']=='mm','Unsupported placement schema/units')
        require(data['project_id']==project_id,'Placement file belongs to another project');require(isinstance(data['placements'],dict),'Invalid placements')
        for key,value in data['placements'].items():identifier(key,'Placement instance');pose(value['translation_mm'],value['rotation_deg'])
        return data
    except (OSError,json.JSONDecodeError,KeyError,TypeError) as error:raise ImportErrorDetail('Cannot read placements: '+str(error)) from error


def reconcile_placements(export,stored):
    require(stored['project_id']==export['project']['id'],'Placement project mismatch')
    result=deepcopy(stored)
    for instance in export['instances']:result['placements'].setdefault(instance['id'],pose())
    return result  # Retain absent IDs so temporarily removed instances can recover later.


def save_placements(path,stored,export_path=None):
    target=Path(path)
    if export_path:require(target.resolve()!=Path(export_path).resolve(),'Placement file must be separate from the AMCAD export')
    if target.exists():
        existing=load_placements(target,stored['project_id'])
        require(existing['schema']=='amcad.placements','Choose a separate placement file')
    for key,value in stored['placements'].items():identifier(key,'Placement instance');pose(value['translation_mm'],value['rotation_deg'])
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=str(target.parent),prefix='.amcad-placement-',delete=False) as stream:
            temporary=stream.name;json.dump(stored,stream,indent=2,allow_nan=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,str(target))
    finally:
        if temporary and os.path.exists(temporary):os.unlink(temporary)


def world_interfaces(cavity,instance_id,placement):
    transform=matrix(placement);result=[]
    for interface in cavity['interfaces']:
        item=deepcopy(interface);item['instance_id']=instance_id
        item['position_mm']=transform_point(transform,item['position_mm'])
        for key in ('direction','section_u','section_v'):item[key]=transform_vector(transform,item[key])
        result.append(item)
    return result


def apply_parameters(export,stored,ids,values):
    """GH list inputs target IDs explicitly; empty lists preserve saved placement values."""
    current={i['id'] for i in export['instances']}
    ids=list(ids) if ids else sorted(current)
    require(len(ids)==len(set(ids)) and all(key in current for key in ids),'Placement parameter IDs must be unique exported instances')
    for name,column in values.items():
        require(name in ('X','Y','Z','Rx','Ry','Rz'),'Unknown placement variable: '+name)
        if not column:continue
        require(len(column)==len(ids),'Supply one '+name+' value per selected instance ID; no implicit broadcasting')
        field='translation_mm' if name in ('X','Y','Z') else 'rotation_deg'
        axis=('X','Y','Z').index(name) if field=='translation_mm' else ('Rx','Ry','Rz').index(name)
        for key,value in zip(ids,column):stored['placements'][key][field][axis]=number(value,name)
    return stored
