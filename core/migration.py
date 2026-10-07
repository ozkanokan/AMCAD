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
