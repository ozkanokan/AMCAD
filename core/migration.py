"""Deterministic V1 loading migration; original files are never rewritten on open."""
from copy import deepcopy
from dataclasses import asdict
from uuid import NAMESPACE_URL, uuid5
from core.junction import junction_definition
from core.geometry import SIDE_VECTORS, rotated_side


def migrate_v1(original):
    data = deepcopy(original)
    nodes = {n['id']: n for n in data['nodes']}
    instances = {i['id']: i for i in data['component_instances']}
    definitions = {d['id']: d for d in data['component_definitions']}
    for records in ('nodes', 'component_instances', 'component_definitions', 'connections'):
        if len({r['id'] for r in data[records]}) != len(data[records]):
            raise ValueError(f'Duplicate ID in {records}')
    if set(data['junctions']) != {n['id'] for n in nodes.values() if n['kind'] == 'junction'}:
        raise ValueError('Junction index disagrees with nodes')
    pairs = set()
    for c in data['connections']:
        a, b = c['from_node_id'], c['to_node_id']
        if a not in nodes or b not in nodes or a == b:
            raise ValueError('Invalid connection endpoints')
        pair = frozenset((a, b))
        if pair in pairs:
            raise ValueError('Duplicate connection')
        pairs.add(pair)

    legacy_ids = {d['id'] for d in definitions.values()
                  if d.get('symbol', {}).get('kind') == 'junction' and len(d['ports']) == 1}
    additions = {}
    for instance in instances.values():
        if instance['definition_id'] not in legacy_ids:
            continue
        old_definition = definitions[instance['definition_id']]
        old_nodes = [n for n in nodes.values() if n['instance_id'] == instance['id']]
        if len(old_nodes) != 1 or old_nodes[0]['port_id'] != old_definition['ports'][0]['id']:
            raise ValueError('Invalid legacy junction nodes')
        old_node = old_nodes[0]
        if old_node['kind'] != 'junction':
            raise ValueError('Invalid legacy junction kind')
        incident = [c for c in data['connections'] if old_node['id'] in (c['from_node_id'], c['to_node_id'])]
        if len(incident) > 4:
            raise ValueError('Legacy junction has more than four branches; split it before upgrading to V1.1')
        ways = 3 if len(incident) <= 3 else 4
        definition_id = str(uuid5(NAMESPACE_URL, f"amcad:junction:{old_definition['id']}:{ways}"))
        definition = junction_definition(ways, definition_id)
        if definition_id in definitions and definitions[definition_id] != definition.to_dict():
            raise ValueError('Migrated junction definition ID collides with an existing definition')
        additions[definition_id] = definition.to_dict()
        instance['definition_id'] = definition_id
        available = list(definition.ports)
        assignments = []
        for connection in incident:
            key = 'from_node_id' if connection['from_node_id'] == old_node['id'] else 'to_node_id'
            other_key = 'to_node_id' if key == 'from_node_id' else 'from_node_id'
            other = instances[nodes[connection[other_key]]['instance_id']]
            dx, dy = other['x'] - instance['x'], other['y'] - instance['y']
            def score(port):
                vx, vy = SIDE_VECTORS[rotated_side(port.side, instance['rotation'])]
                return dx * vx + dy * vy
            port = max(available, key=score)
            available.remove(port)
            assignments.append((port, connection, key))
        assignments.extend((port, None, None) for port in available)
        del nodes[old_node['id']]
        for index, (port, connection, key) in enumerate(assignments):
            # Keep the legacy node UUID for the first endpoint; derive other UUIDs
            # deterministically so repeated opening preserves migrated identities.
            node_id = old_node['id'] if index == 0 else str(uuid5(NAMESPACE_URL, f"amcad:node:{old_node['id']}:{port.id}"))
            if node_id in nodes:
                raise ValueError('Migrated node ID collides with an existing node')
            nodes[node_id] = {'id': node_id, 'instance_id': instance['id'], 'port_id': port.id, 'kind': 'junction'}
            if connection is not None:
                connection[key] = node_id
    data['component_definitions'] = [d for d in definitions.values() if d['id'] not in legacy_ids] + list(additions.values())
    data['nodes'] = list(nodes.values())
    data['junctions'] = [n['id'] for n in nodes.values() if n['kind'] == 'junction']
    for c in data['connections']:
        for end in ('from', 'to'):
            node = nodes[c[f'{end}_node_id']]
            c[f'{end}_component_instance_id'] = node['instance_id']
            c[f'{end}_port_id'] = node['port_id']
    data['schema_version'] = 2
    return data


def migrate_v2_branches(original):
    """Authorized legacy-only conversion of implicit fan-outs into explicit junctions."""
    data=deepcopy(original)
    nodes={n['id']:n for n in data['nodes']}
    instances={i['id']:i for i in data['component_instances']}
    definitions={d['id']:d for d in data['component_definitions']}
    for records in ('nodes','component_instances','component_definitions','connections'):
        if len({record['id'] for record in data[records]})!=len(data[records]):
            raise ValueError(f'Duplicate legacy object IDs in {records}')
    names={i['name'] for i in instances.values()}
    used=set(nodes)|set(instances)|set(definitions)|{c['id'] for c in data['connections']}
    def identifier(text):
        value=str(uuid5(NAMESPACE_URL,'amcad:v1.2:'+text))
        if value in used: raise ValueError('Legacy migration ID collision')
        used.add(value)
        return value
    original_nodes=list(nodes.values())
    original_edges=list(data['connections'])
    pairs=set()
    for c in original_edges:
        a,b=c['from_node_id'],c['to_node_id']
        if a not in nodes or b not in nodes or a==b: raise ValueError('Invalid legacy endpoints')
        if frozenset((a,b)) in pairs: raise ValueError('Duplicate legacy line')
        pairs.add(frozenset((a,b)))
        for end in ('from','to'):
            node=nodes[c[f'{end}_node_id']]
            if (c[f'{end}_component_instance_id'],c[f'{end}_port_id'])!=(node['instance_id'],node['port_id']):
                raise ValueError('Connection instance/port references disagree with node IDs')
    for node in original_nodes:
        incident=[c for c in original_edges if node['id'] in (c['from_node_id'],c['to_node_id'])]
        if len(incident)<=1: continue
        if node['kind']=='junction': raise ValueError('Invalid overoccupied V1.1 junction port')
        root=instances[node['instance_id']]
        ways=3 if len(incident)==2 else 4 if len(incident)==3 else 3
        count=1 if len(incident)<=3 else len(incident)-1
        definition_id=str(uuid5(NAMESPACE_URL,f'amcad:v1.2:migrated-junction-{ways}'))
        definition=junction_definition(ways,definition_id).to_dict()
        if definition_id in definitions and definitions[definition_id]!=definition:
            raise ValueError('Legacy junction definition collision')
        definitions[definition_id]=definition
        previous=node['id']; remaining=list(incident)
        for index in range(count):
            instance_id=identifier(f"{node['id']}:junction:{index}")
            number=1
            while f'J_Migrated{number}' in names: number+=1
            name=f'J_Migrated{number}'; names.add(name)
            instance={'id':instance_id,'definition_id':definition_id,'name':name,
                      'x':root['x']+100+index*80,'y':root['y']+80,'rotation':0}
            instances[instance_id]=instance
            port_nodes={}
            for port in definition['ports']:
                nid=identifier(f"{instance_id}:port:{port['id']}")
                nodes[nid]={'id':nid,'instance_id':instance_id,'port_id':port['id'],'kind':'junction'}
                port_nodes[port['id']]=nid
            edge={'id':identifier(f"{instance_id}:link"),'from_node_id':previous,'to_node_id':port_nodes['LEFT']}
            data['connections'].append(edge)
            branch_ports=[p for p in port_nodes if p!='LEFT']
            if index<count-1:
                previous=port_nodes[branch_ports.pop()]
                branch_ports=branch_ports[:1]
            for port_id in branch_ports:
                connection=remaining.pop(0)
                key='from_node_id' if connection['from_node_id']==node['id'] else 'to_node_id'
                connection[key]=port_nodes[port_id]
        assert not remaining
    for c in data['connections']:
        for end in ('from','to'):
            node=nodes[c[f'{end}_node_id']]
            c[f'{end}_component_instance_id']=node['instance_id']
            c[f'{end}_port_id']=node['port_id']
            c.pop('schematic_geometry',None)
    data['component_definitions']=list(definitions.values())
    data['component_instances']=list(instances.values())
    data['nodes']=list(nodes.values())
    data['junctions']=[n['id'] for n in nodes.values() if n['kind']=='junction']
    return data
