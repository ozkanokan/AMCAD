"""Pure diagram geometry and gestures. Coordinates here never place physical cavities."""
import math
try:
    from .topology_core import key
except ImportError:
    from topology_core import key


def distance_segment(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]; length = dx*dx+dy*dy
    t = max(0., min(1., ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length)) if length else 0
    return math.hypot(p[0]-a[0]-t*dx, p[1]-a[1]-t*dy)


class Diagram:
    def __init__(self, model):
        self.model = model; self.zoom = 1.; self.offset = [40., 50.]
        self.selection = None; self.pending = []; self.y_mode = False
        self.reconnect = None; self.drag = None; self.cursor = (0., 0.)
        self.names = {}; self.instance_names = {}
        for node in model.source_graph.get('nodes', []):
            t = node.get('physical_terminal')
            if not t: continue
            ref = key(t); name = str(node.get('name', ref[1]))
            self.names[ref] = name.rsplit('.', 1)[-1]
            self.instance_names[ref[0]] = name.rsplit('.', 1)[0] if '.' in name else name
        for ref, p in model.all_ports().items():
            self.names.setdefault(ref, p.get('label', ref[1][:12]))
            self.instance_names.setdefault(ref[0], p.get('instance_name', 'Cavity '+ref[0][:8]))

    def screen(self, p): return (p[0]*self.zoom+self.offset[0], p[1]*self.zoom+self.offset[1])
    def world(self, p): return ((p[0]-self.offset[0])/self.zoom, (p[1]-self.offset[1])/self.zoom)

    def zoom_at(self, screen, factor):
        p = self.world(screen); self.zoom = max(.25, min(3., self.zoom*factor))
        self.offset = [screen[i]-p[i]*self.zoom for i in (0, 1)]

    def blocks(self):
        ids = sorted({r[0] for r in self.model.all_ports()}, key=lambda i: (self.instance_names.get(i, i), i))
        result = {}
        for index, iid in enumerate(ids):
            refs = [r for r in self.model.all_ports() if r[0] == iid]
            pos = self.model.doc['layout'].get('cavity:'+iid, [(index%3)*290., (index//3)*210.])
            result[iid] = (pos[0], pos[1], 210., max(95., 45.+math.ceil(len(refs)/2)*28.))
        return result

    def ports(self):
        result = {}; blocks = self.blocks()
        for iid, (x,y,w,h) in blocks.items():
            refs = [r for r in self.model.all_ports() if r[0] == iid]
            for index, ref in enumerate(refs):
                result[ref] = (x if index%2==0 else x+w, y+46.+(index//2)*28.)
        return result

    def groups(self):
        ports = self.ports(); result = {}
        for g in self.model.doc['groups']:
            points = [ports[tuple(r)] for r in g['ports']]
            if len(points) == 2:
                a,b = points; mid = (a[0]+b[0])/2
                result[g['id']] = {'center': None, 'paths': [[a,(mid,a[1]),(mid,b[1]),b]]}
            else:
                center = self.model.doc['layout'].get('junction:'+g['id'], [sum(p[i] for p in points)/3 for i in (0,1)])
                result[g['id']] = {'center': center, 'paths': [[p,center] for p in points]}
        return result

    def hit(self, screen):
        p = self.world(screen); radius = 9./self.zoom
        for ref, q in self.ports().items():
            if math.dist(p,q) <= radius: return ('port',ref)
        for gid, g in self.groups().items():
            if g['center'] and math.dist(p,g['center']) <= 11./self.zoom: return ('junction',gid)
        for iid, (x,y,w,h) in reversed(list(self.blocks().items())):
            if x<=p[0]<=x+w and y<=p[1]<=y+h: return ('cavity',iid)
        for gid,g in self.groups().items():
            if any(distance_segment(p,a,b) <= 6./self.zoom for path in g['paths'] for a,b in zip(path,path[1:])):
                return ('group',gid)
        return None

    def choose_port(self, ref):
        if ref in {tuple(x) for x in self.model.doc['disabled']}: raise ValueError('Enable the port before connecting it')
        if self.reconnect:
            gid,index = self.reconnect; self.model.reconnect(gid,index,ref); self.cancel(); return
        if ref not in self.pending: self.pending.append(ref)
        count = 3 if self.y_mode else 2
        if len(self.pending) == count:
            try: self.model.add_group(self.pending)
            finally: self.pending = []

    def down(self, screen, pan=False):
        self.cursor = self.world(screen)
        if pan:
            self.drag = ('pan',tuple(screen),list(self.offset)); return
        self.selection = self.hit(screen)
        if not self.selection: return
        kind, ident = self.selection
        if kind in ('cavity','junction'):
            storage = kind+':'+ident
            pos = self.blocks()[ident][:2] if kind == 'cavity' else self.groups()[ident]['center']
            self.drag = (storage,self.world(screen),list(pos))
        elif kind == 'port':
            owner = next((g for g in self.model.doc['groups'] if list(ident) in g['ports']),None)
            if self.pending or self.reconnect: self.choose_port(ident)
            elif owner and not self.y_mode:
                self.reconnect = (owner['id'],owner['ports'].index(list(ident)))
            else: self.choose_port(ident)

    def move(self, screen):
        self.cursor = self.world(screen)
        if not self.drag: return
        ident, start, origin = self.drag
        if ident == 'pan': self.offset = [origin[i]+screen[i]-start[i] for i in (0,1)]
        else:
            now = self.world(screen)
            self.model.doc['layout'][ident] = [origin[i]+now[i]-start[i] for i in (0,1)]

    def up(self, screen):
        self.drag = None
        hit = self.hit(screen)
        if hit and hit[0] == 'port' and (self.pending or self.reconnect):
            ref = hit[1]
            if self.reconnect:
                g = next(g for g in self.model.doc['groups'] if g['id']==self.reconnect[0])
                if tuple(g['ports'][self.reconnect[1]]) == ref: return
            if ref not in self.pending: self.choose_port(ref)

    def cancel(self): self.pending = []; self.reconnect = None; self.drag = None

    def delete_selected(self):
        if not self.selection: return
        kind, ident = self.selection
        if kind in ('group','junction'): self.model.delete_group(ident)
        elif kind == 'port':
            if ident in self.model.base: self.model.set_disabled(ident, True)
            else: self.model.remove_port(ident)
        else: raise ValueError('Cavity blocks are source instances; select a connection or physical port')
        self.selection = None; self.cancel()
