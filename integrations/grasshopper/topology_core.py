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
    value = p.get('id', p.get('interface_id'))
    if not isinstance(p.get('instance_id'), str) or not p['instance_id'].strip() or not isinstance(value, str) or not value.strip():
        raise ValueError('Port needs nonempty instance and interface IDs')
    return (p['instance_id'], value)


def label(k):
    return '{} / {}'.format(k[0], k[1])


def _finite_vector(v, name):
    if not isinstance(v, (tuple, list)) or len(v) != 3:
        raise ValueError('{} must be 3 numbers'.format(name))
    result = [_number(x, name) for x in v]
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
        v = _number(section[field], field)
        if not math.isfinite(v) or v <= 0:
            raise ValueError('Invalid section {}'.format(field))
    key(p)
    _validate_frame(p)
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
        self.doc.setdefault('layout', {})
        self.validate()

    def all_ports(self):
        merged = dict(self.base)
        for p in self.doc['extra_ports']:
            k = key(p)
            if k in merged:
                raise ValueError('Additional port collides with existing port {}'.format(k))
            merged[k] = resolve_port(p, self.base)
        return merged

    def validate(self):
        ports = self.all_ports()
        disabled = {tuple(x) for x in self.doc['disabled']}
        if len(disabled) != len(self.doc['disabled']):
            raise ValueError('Duplicate disabled port')
        if not disabled.issubset(ports):
            raise ValueError('Disabled port not present')
        for p in self.doc['extra_ports']:
            validate_extra(ports[key(p)])
            if key(p)[0] not in {k[0] for k in self.base}:
                raise ValueError('Additional port instance is missing')
        for point in self.doc.get('layout', {}).values():
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise ValueError('Diagram positions need two coordinates')
            for value in point: _number(value, 'Diagram position')
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
        before = copy.deepcopy(self.doc)
        ref = list(ref)
        self.doc['disabled'] = [x for x in self.doc['disabled'] if x != ref]
        if disabled:
            self.doc['disabled'].append(ref)
        try: self.validate()
        except Exception:
            self.doc = before
            raise

    def reconnect(self, gid, index, ref):
        before = copy.deepcopy(self.doc)
        try:
            group = next(g for g in self.doc['groups'] if g['id'] == gid)
            group['ports'][index] = list(ref)
            self.validate()
        except Exception:
            self.doc = before
            raise

    def edit_group(self, gid, refs):
        """Replace endpoints atomically, retaining the route ID and its settings."""
        before = copy.deepcopy(self.doc)
        try:
            group = next(g for g in self.doc['groups'] if g['id'] == gid)
            group['ports'] = [list(ref) for ref in refs]
            self.validate()
        except Exception:
            self.doc = before
            raise

    def remove_port(self, ref):
        ref = tuple(ref)
        if ref in self.base: raise ValueError('Original ports can be disabled, not removed')
        if any(list(ref) in g['ports'] for g in self.doc['groups']):
            raise ValueError('Disconnect the port before removing it')
        self.doc['extra_ports'] = [p for p in self.doc['extra_ports'] if key(p) != ref]
        self.doc['disabled'] = [p for p in self.doc['disabled'] if tuple(p) != ref]

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
        metadata += [copy.deepcopy(p) for k,p in self.all_ports().items() if k not in self.base and k not in disabled]
        graph = copy.deepcopy(self.source_graph)
        graph['nets'] = [
            {'id': g['id'], 'terminals': [{'instance_id': x[0], 'interface_id': x[1]} for x in g['ports']]}
            for g in self.doc['groups']
        ]
        # Private routing projection only. Keep the input logical graph immutable.
        # Added nodes supply names to Channel Diameter Editor v12e.
        graph.setdefault('nodes', [])
        for p in self.doc['extra_ports']:
            graph['nodes'].append({'id': 'physical:' + p['id'], 'instance_id': p['instance_id'],
                'name': p.get('label', p['id']),
                'physical_terminal': {'instance_id': p['instance_id'], 'interface_id': p['id']}})
        return [json.dumps(p) for p in metadata], json.dumps(graph)

    def save(self, path):
        self.validate()
        if os.path.exists(path):
            old = self.load(path)
            if not isinstance(old, dict) or old.get('schema') != VERSION or not isinstance(old.get('groups'), list) or not isinstance(old.get('extra_ports'), list):
                raise ValueError('Choose a separate topology sidecar, not an export/project/placement file')
        folder = os.path.dirname(os.path.abspath(path))
        fd, tmp = tempfile.mkstemp(prefix='.amcad_topology_', suffix='.tmp', dir=folder)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(self.doc, f, indent=2, ensure_ascii=False, allow_nan=False)
                f.flush(); os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    @staticmethod
    def load(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

# v1 sidecars remain readable; optional diagram/binding fields are additive.
def frame(direction, rotation_deg=0):
    """Right-handed unit section frame using AMCAD's least-aligned-axis convention."""
    d = _unit(direction, 'direction')
    axes = ([1., 0., 0.], [0., 1., 0.], [0., 0., 1.])
    axis = min(axes, key=lambda a: abs(_dot(a, d)))
    u = _unit(_cross(axis, d), 'section_u'); v = _cross(d, u)
    a = math.radians(_number(rotation_deg, 'section rotation'))
    return ([u[i]*math.cos(a)+v[i]*math.sin(a) for i in range(3)],
            [-u[i]*math.sin(a)+v[i]*math.cos(a) for i in range(3)])


def _number(value, name):
    if isinstance(value, bool): raise ValueError(name + ' must be a finite number')
    result = float(value)
    if not math.isfinite(result): raise ValueError(name + ' must be finite')
    return result


def _dot(a, b): return sum(x*y for x, y in zip(a, b))
def _cross(a, b): return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def _unit(value, name):
    v = _finite_vector(value, name); length = math.hypot(*v)
    if length < 1e-12: raise ValueError('Zero ' + name)
    return [x/length for x in v]


def make_port(instance_id, name, position, direction, section, rotation_deg=0):
    """Complete world-space Port Preparation v17 metadata, never a visual-only port."""
    if not str(name).strip(): raise ValueError('Port name is required')
    d = _unit(direction, 'direction'); u, v = frame(d, rotation_deg)
    p = {'instance_id': str(instance_id), 'id': 'extra_' + str(uuid.uuid4()),
         'label': str(name).strip(), 'position_mm': _finite_vector(position, 'position_mm'),
         'direction': d, 'section_u': u, 'section_v': v, 'section': copy.deepcopy(section)}
    validate_extra(p)
    return p


def bind_port(port, reference):
    """Attach world geometry to the original interface's rigid frame; no new GH pose input."""
    p = copy.deepcopy(port)
    basis = [reference['section_u'], reference['section_v'], reference['direction']]
    _validate_frame(reference)
    delta = [p['position_mm'][i]-reference['position_mm'][i] for i in range(3)]
    binding = {'reference_interface_id': key(reference)[1], 'position': [_dot(delta, b) for b in basis]}
    for field in ('direction', 'section_u', 'section_v'):
        binding[field] = [_dot(p[field], b) for b in basis]
    p['binding'] = binding
    return p


def resolve_port(port, base):
    p = copy.deepcopy(port); binding = p.get('binding')
    if binding is None: return p  # Legacy v1 extras are explicitly world-fixed.
    ref = (p['instance_id'], str(binding['reference_interface_id']))
    if ref not in base: raise ValueError('Additional port attachment is missing: ' + str(ref))
    host = base[ref]; _validate_frame(host)
    basis = [host['section_u'], host['section_v'], host['direction']]
    for field in ('position', 'direction', 'section_u', 'section_v'):
        local = _finite_vector(binding[field], 'binding ' + field)
        world = [sum(local[j]*basis[j][i] for j in range(3)) for i in range(3)]
        if field == 'position': p['position_mm'] = [host['position_mm'][i]+world[i] for i in range(3)]
        else: p[field] = world
    return p


def _validate_frame(p):
    d, u, v = [_finite_vector(p[x], x) for x in ('direction', 'section_u', 'section_v')]
    if any(abs(math.hypot(*x)-1) > 1e-7 for x in (d, u, v)) or any(abs(_dot(a,b)) > 1e-7 for a,b in ((u,v),(d,u),(d,v))) or math.dist(_cross(u,v), d) > 1e-7:
        raise ValueError('Port section frame must be orthonormal and right-handed')


class Draft:
    """Testable draft/publish boundary. Drawing never schedules GH or writes files."""
    def __init__(self, state, on_apply):
        self.state = state; self.on_apply = on_apply
        self.model = Topology(state['metadata'], state['connectivity'], state['model'].doc)
        self.baseline = copy.deepcopy(state['model'].doc)

    def publish(self, save=True, trace=None):
        log=trace or (lambda message:None)
        if not save: raise ValueError('Only Save may publish topology changes to Grasshopper')
        if self.state['model'].doc != self.baseline:
            raise ValueError('Applied topology changed; discard/reopen this draft before applying')
        log('Build/validate publication snapshot START')
        candidate = Topology(self.state['metadata'], self.state['connectivity'], self.model.doc)
        log('Build/validate publication snapshot DONE')
        if save:
            log('Atomic sidecar write START')
            candidate.save(self.state['path'])
            log('Atomic sidecar write DONE')
        self.state['model'] = candidate; self.baseline = copy.deepcopy(candidate.doc)
        if save: self.state['saved_doc'] = copy.deepcopy(candidate.doc)
        log('Request GH update START')
        self.on_apply()
        log('Request GH update RETURNED')

    def discard(self):
        self.model = Topology(self.state['metadata'], self.state['connectivity'], self.state['model'].doc)
        self.baseline = copy.deepcopy(self.state['model'].doc)
