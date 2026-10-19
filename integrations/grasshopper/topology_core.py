"""AMCAD physical topology editor core, v1. No Rhino dependencies.

Physical route groups are projected to the EXISTING Connectivity v3 contract:
  {"nets": [{"id": unique_route_id, "terminals": [{"instance_id":...,"interface_id":...}, ...]}]}
Each group must have 2 (PAIR) or 3 (Y) distinct physical ports.
A port can only participate in one group; original logical net provenance is kept
in the separate sidecar, NOT passed to the legacy solver as its routing net_id.
"""
import copy
import json
import math
import os
import tempfile
import uuid

VERSION = 1


def decode(value):
    if hasattr(value, 'Value'):
        value = value.Value
    return json.loads(value) if isinstance(value, str) else value


def flatten(value):
    if value is None:
        return []
    if hasattr(value, 'Branches'):
        return [item for branch in value.Branches for item in branch]
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def key(p):
    return (str(p['instance_id']), str(p.get('id', p.get('interface_id'))))


def label(k):
    return '{} / {}'.format(k[0], k[1])


def _finite_vector(v, name):
    if not isinstance(v, (tuple, list)) or len(v) != 3:
        raise ValueError('{} must be 3 numbers'.format(name))
    result = [float(x) for x in v]
    if not all(math.isfinite(x) for x in result):
        raise ValueError('{} contains non-finite numbers'.format(name))
    return result


def validate_extra(p):
    required = ('instance_id', 'id', 'position_mm', 'direction', 'section', 'section_u', 'section_v')
    for field in required:
        if field not in p:
            raise ValueError('Additional port missing {}'.format(field))
    for name in ('position_mm', 'direction', 'section_u', 'section_v'):
        v = _finite_vector(p[name], name)
        if name != 'position_mm' and sum(x*x for x in v) < 1e-12:
            raise ValueError('Zero {}'.format(name))
    section = p['section']
    if not isinstance(section, dict):
        raise ValueError('section must be object')
    shape = section.get('type')
    fields = {'CIRCLE': ('diameter_mm',), 'RECTANGLE': ('width_mm', 'height_mm'),
              'SLOT': ('width_mm', 'height_mm')}.get(shape)
    if fields is None:
        raise ValueError('Unsupported section {}'.format(shape))
    for field in fields:
        v = float(section[field])
        if not math.isfinite(v) or v <= 0:
            raise ValueError('Invalid section {}'.format(field))
    # v1 only supports fully resolved world-space geometry, NOT profile anchors.
    return p


class Topology:
    def __init__(self, metadata, connectivity, sidecar=None):
        self.original = [copy.deepcopy(decode(x)) for x in flatten(metadata)]
        self.source_graph = copy.deepcopy(decode(connectivity))
        if not isinstance(self.source_graph, dict) or not isinstance(self.source_graph.get('nets'), list):
            raise ValueError('Connectivity must contain nets list')
        self.base = {key(p): p for p in self.original}
        if len(self.base) != len(self.original):
            raise ValueError('Duplicate original port identity')
        if sidecar is None:
            groups = []
            unresolved = []
            for net in self.source_graph['nets']:
                terminals = net.get('terminals', [])
                if len(terminals) in (2, 3):
                    groups.append({'id': str(net.get('id', len(groups))),
                                   'source_net_id': str(net.get('id', '')),
                                   'ports': [list(key(p)) for p in terminals]})
                elif terminals:
                    unresolved.append(str(net.get('id', '?')))
            self.doc = {'schema': VERSION, 'groups': groups, 'extra_ports': [],
                        'disabled': [], 'unresolved_source_nets': unresolved}
        else:
            self.doc = copy.deepcopy(decode(sidecar))
            if self.doc.get('schema') != VERSION:
                raise ValueError('Unsupported topology sidecar schema')
        # Existing sidecars retain their exact route IDs to protect
        # previously saved Channel Diameter Editor settings.
        self.validate()

    def all_ports(self):
        merged = dict(self.base)
        for p in self.doc['extra_ports']:
            k = key(p)
            if k in merged:
                raise ValueError('Additional port collides with existing port {}'.format(k))
            merged[k] = p
        return merged

    def validate(self):
        ports = self.all_ports()
        disabled = {tuple(x) for x in self.doc['disabled']}
        if len(disabled) != len(self.doc['disabled']):
            raise ValueError('Duplicate disabled port')
        if not disabled.issubset(ports):
            raise ValueError('Disabled port not present')
        for p in self.doc['extra_ports']:
            validate_extra(p)
        seen_ports = set()
        seen_groups = set()
        for group in self.doc['groups']:
            gid = str(group['id'])
            if not gid or gid in seen_groups:
                raise ValueError('Duplicate/empty route group ID')
            seen_groups.add(gid)
            refs = [tuple(x) for x in group['ports']]
            if len(refs) not in (2, 3):
                raise ValueError('{} requires 2 or 3 physical ports'.format(gid))
            if len(set(refs)) != len(refs):
                raise ValueError('Repeated port in {}'.format(gid))
            for ref in refs:
                if ref not in ports:
                    raise ValueError('Unknown port {} in {}'.format(ref, gid))
                if ref in disabled:
                    raise ValueError('Disabled port {} in {}'.format(ref, gid))
                if ref in seen_ports:
                    raise ValueError('Port used in multiple route groups: {}'.format(ref))
                seen_ports.add(ref)
        return True

    def add_group(self, refs, source_net_id=''):
        refs = [list(x) for x in refs]
        new = {'id': 'route_' + uuid.uuid4().hex[:12],
               'source_net_id': str(source_net_id), 'ports': refs}
        self.doc['groups'].append(new)
        try:
            self.validate()
        except Exception:
            self.doc['groups'].pop()
            raise
        return new['id']

    def delete_group(self, gid):
        self.doc['groups'] = [x for x in self.doc['groups'] if x['id'] != gid]

    def set_disabled(self, ref, disabled):
        ref = list(ref)
        self.doc['disabled'] = [x for x in self.doc['disabled'] if x != ref]
        if disabled:
            self.doc['disabled'].append(ref)
        self.validate()

    def add_port(self, p):
        p = copy.deepcopy(p)
        p.setdefault('id', 'extra_' + uuid.uuid4().hex[:12])
        validate_extra(p)
        if str(p['instance_id']) not in {str(k[0]) for k in self.base}:
            raise ValueError('Instance is not present in original metadata')
        self.doc['extra_ports'].append(p)
        try:
            self.validate()
        except Exception:
            self.doc['extra_ports'].pop()
            raise
        return key(p)

    def outputs(self):
        self.validate()
        disabled = {tuple(x) for x in self.doc['disabled']}
        metadata = [copy.deepcopy(p) for p in self.original if key(p) not in disabled]
        metadata += [copy.deepcopy(p) for p in self.doc['extra_ports'] if key(p) not in disabled]
        graph = copy.deepcopy(self.source_graph)
        graph['nets'] = [
            {'id': g['id'], 'terminals': [{'instance_id': x[0], 'interface_id': x[1]} for x in g['ports']]}
            for g in self.doc['groups']
        ]
        return [json.dumps(p) for p in metadata], json.dumps(graph)

    def save(self, path):
        self.validate()
        folder = os.path.dirname(os.path.abspath(path))
        fd, tmp = tempfile.mkstemp(prefix='.amcad_topology_', suffix='.tmp', dir=folder)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(self.doc, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    @staticmethod
    def load(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
