"""Derived surface/channel visualization geometry; no meshes are authoritative data."""
from dataclasses import dataclass
import math


def finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{label} must be finite')
    return value


def add(a, b): return tuple(x+y for x,y in zip(a,b))
def sub(a, b): return tuple(x-y for x,y in zip(a,b))
def mul(a, s): return tuple(x*s for x in a)
def dot(a, b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def normalized(vector):
    if not isinstance(vector,(list,tuple)) or len(vector)!=3:
        raise ValueError('Direction needs three coordinates')
    for v in vector: finite_number(v,'Direction')
    scale=max(abs(v) for v in vector)
    if scale==0: raise ValueError('Direction vector must be nonzero')
    scaled=tuple(v/scale for v in vector); length=math.hypot(*scaled)
    return tuple(v/length for v in scaled)


@dataclass
class SurfaceAnchor:
    kind: str
    vertex_id: str
    next_vertex_id: str | None = None
    t: float = .5
    angle_deg: float = 0

    def validate(self):
        if self.kind not in ('LINE','FILLET','CHAMFER'): raise ValueError('Unknown surface anchor kind')
        if not isinstance(self.vertex_id,str) or not self.vertex_id: raise ValueError('Anchor needs a vertex ID')
        if self.kind=='LINE':
            if not isinstance(self.next_vertex_id,str) or not self.next_vertex_id or self.next_vertex_id==self.vertex_id:
                raise ValueError('Line anchor needs a distinct second vertex ID')
        elif self.next_vertex_id is not None: raise ValueError('Corner anchor has only one vertex ID')
        if not 0<=finite_number(self.t,'Surface parameter')<=1: raise ValueError('Surface parameter must be between 0 and 1')
        finite_number(self.angle_deg,'Circumferential angle')
        return self


@dataclass
class ChannelSection:
    type: str = 'CIRCLE'
    diameter_mm: float = 4
    width_mm: float = 4
    length_mm: float = 8
    height_mm: float = 4

    def validate(self):
        if self.type not in ('CIRCLE','SLOT','RECTANGLE'): raise ValueError('Unknown channel section')
        fields={'CIRCLE':('diameter_mm',),'SLOT':('width_mm','length_mm'),'RECTANGLE':('width_mm','height_mm')}[self.type]
        for name in fields:
            if finite_number(getattr(self,name),'Section dimension')<=0: raise ValueError('Section dimensions must be positive')
        if self.type=='SLOT' and self.length_mm<self.width_mm:
            raise ValueError('Slot overall length must be at least its width')
        return self


@dataclass
class SurfacePatch:
    anchor: SurfaceAnchor
    feature: dict

    def evaluate(self,t):
        f=self.feature
        if f['kind']=='arc':
            a=math.radians(f['start_deg']+f['sweep_deg']*t)
            z=f['center'][0]+f['radius']*math.cos(a)
            r=f['center'][1]+f['radius']*math.sin(a)
            tangent=(-math.sin(a)*f['sweep_deg'],math.cos(a)*f['sweep_deg'])
        else:
            start,end=f['start'],f['end']
            z=start[0]+(end[0]-start[0])*t; r=start[1]+(end[1]-start[1])*t
            tangent=(end[0]-start[0],end[1]-start[1])
        return (z,max(0,r)),tangent


def surface_patches(profile):
    """IDs refer to adjacent theoretical vertices or a typed corner, never mesh indices."""
    features=profile.features(); result=[]
    if features and features[0]['kind']!='sharp':
        feature=features[0]; kind='FILLET' if feature['kind']=='arc' else 'CHAMFER'
        result.append(SurfacePatch(SurfaceAnchor(kind,profile.vertices[0].id),feature if kind=='FILLET' else {'kind':'line','start':feature['entry'],'end':feature['exit']}))
    for i in range(1,len(profile.vertices)):
        previous,vertex=profile.vertices[i-1:i+1]
        result.append(SurfacePatch(SurfaceAnchor('LINE',previous.id,vertex.id),
                                  {'kind':'line','start':features[i-1]['exit'],'end':features[i]['entry']}))
        feature=features[i]
        if feature['kind']=='arc':
            result.append(SurfacePatch(SurfaceAnchor('FILLET',vertex.id),feature))
        elif feature['kind']=='chamfer':
            result.append(SurfacePatch(SurfaceAnchor('CHAMFER',vertex.id),
                                      {'kind':'line','start':feature['entry'],'end':feature['exit']}))
    return result


def anchor_key(anchor): return (anchor.kind,anchor.vertex_id,anchor.next_vertex_id)


def resolve_anchor(profile,anchor):
    anchor.validate()
    patch=next((p for p in surface_patches(profile) if anchor_key(p.anchor)==anchor_key(anchor)),None)
    if patch is None: raise ValueError('Surface anchor no longer resolves to its original segment/feature')
    (z,r),(dz,dr)=patch.evaluate(anchor.t)
    angle=math.radians(anchor.angle_deg)
    xyz=(r*math.cos(angle),r*math.sin(angle),z)
    # Closed boundaries use traversal orientation to point from void into material.
    # Legacy open profiles keep their historical radial-facing normal.
    normal=(dz*math.cos(angle),dz*math.sin(angle),-dr)
    if profile.axis_closed():
        raw=[(v.z,v.r) for v in profile.vertices]
        area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(raw,raw[1:]+raw[:1]))
        if area>0: normal=mul(normal,-1)
    elif dz<0: normal=mul(normal,-1)
    return xyz,normalized(normal)


@dataclass
class Mesh:
    vertices: list
    triangles: list
    anchors: list | None = None  # Per-triangle parametric pick information for cavity only.


def revolved_surface(profile,angular_steps=64,arc_steps=16):
    if angular_steps<8 or arc_steps<1: raise ValueError('Insufficient surface tessellation')
    vertices=[]; triangles=[]; anchors=[]
    for patch in surface_patches(profile):
        steps=max(2,math.ceil(abs(patch.feature['sweep_deg'])/90*arc_steps)) if patch.feature['kind']=='arc' else 1
        base=len(vertices)
        for row in range(steps+1):
            (z,r),_=patch.evaluate(row/steps)
            for col in range(angular_steps+1):
                a=2*math.pi*col/angular_steps
                vertices.append((r*math.cos(a),r*math.sin(a),z))
        for row in range(steps):
            for col in range(angular_steps):
                ids=(base+row*(angular_steps+1)+col,base+row*(angular_steps+1)+col+1,
                     base+(row+1)*(angular_steps+1)+col,base+(row+1)*(angular_steps+1)+col+1)
                for indices,parameters in [((ids[0],ids[1],ids[2]),((row/steps,col*360/angular_steps),(row/steps,(col+1)*360/angular_steps),((row+1)/steps,col*360/angular_steps))),
                                           ((ids[1],ids[3],ids[2]),((row/steps,(col+1)*360/angular_steps),((row+1)/steps,(col+1)*360/angular_steps),((row+1)/steps,col*360/angular_steps)))]:
                    triangles.append(indices); anchors.append((patch.anchor,parameters))
    # Axis endpoints converge naturally; do not revolve the virtual closure edge.
    return Mesh(vertices,triangles,anchors)


def interface_pose(profile,interface):
    if interface.surface_anchor is not None:
        position,normal=resolve_anchor(profile,interface.surface_anchor)
    else:
        position=(0,interface.r_mm or 0,interface.z_mm)
        radial=(0,1,0)
        normal=(0,0,-1) if interface.preferred_direction=='AXIAL_NEGATIVE' else (0,0,1) if interface.preferred_direction=='AXIAL_POSITIVE' else radial if interface.preferred_direction=='RADIAL' or interface.interface_type=='RADIAL' else (0,0,1)
    return position,normalized(interface.direction if interface.direction is not None else normal)


def section_frame(direction,rotation_deg=0):
    d=normalized(direction)
    finite_number(rotation_deg,'Section rotation')
    # Choose the least-aligned world axis, breaking ties X, Y, Z deterministically.
    axes=((1,0,0),(0,1,0),(0,0,1)); reference=min(axes,key=lambda axis:abs(dot(d,axis)))
    u=normalized(cross(reference,d)); v=cross(d,u)
    a=math.radians(rotation_deg)
    return add(mul(u,math.cos(a)),mul(v,math.sin(a))),add(mul(u,-math.sin(a)),mul(v,math.cos(a)))


def section_outline(section,steps=32):
    section.validate()
    if section.type=='CIRCLE':
        return [(section.diameter_mm/2*math.cos(i*2*math.pi/steps),section.diameter_mm/2*math.sin(i*2*math.pi/steps)) for i in range(steps)]
    if section.type=='RECTANGLE':
        w,h=section.width_mm/2,section.height_mm/2
        return [(-w,-h),(w,-h),(w,h),(-w,h)]
    radius=section.width_mm/2; offset=(section.length_mm-section.width_mm)/2
    # Capsule long axis is local U; overall length includes the two round ends.
    count=max(8,steps//2)
    return [(offset+radius*math.cos(-math.pi/2+i*math.pi/count),radius*math.sin(-math.pi/2+i*math.pi/count)) for i in range(count+1)]+[(-offset+radius*math.cos(math.pi/2+i*math.pi/count),radius*math.sin(math.pi/2+i*math.pi/count)) for i in range(count+1)]


def channel_mesh(profile,interface):
    position,direction=interface_pose(profile,interface)
    section=interface.section or ChannelSection(diameter_mm=interface.nominal_connection_diameter_mm)
    length=finite_number(interface.preview_length_mm,'Preview length')
    if length<=0: raise ValueError('Preview length must be positive')
    u,v=section_frame(direction,interface.section_rotation_deg)
    outline=section_outline(section)
    start_position=add(position,mul(direction,-length/2)) if interface.preview_mode=='CENTERED' else position
    start=[add(start_position,add(mul(u,a),mul(v,b))) for a,b in outline]
    end=[add(p,mul(direction,length)) for p in start]
    n=len(outline); vertices=start+end+[start_position,add(start_position,mul(direction,length))]; triangles=[]
    for i in range(n):
        j=(i+1)%n
        triangles.extend([(i,j,n+i),(j,n+j,n+i),(2*n,j,i),(2*n+1,n+i,n+j)])
    return Mesh(vertices,triangles)


def legacy_surface_anchor(profile,interface,tolerance=1e-8):
    """Exact legacy location only. Axis locations have no known circumferential angle."""
    if interface.surface_anchor is not None: return interface.surface_anchor
    position,_=interface_pose(profile,interface); z,r=position[2],math.hypot(*position[:2])
    if r<=tolerance: return None
    for patch in surface_patches(profile):
        f=patch.feature
        if f['kind']=='arc':
            a=math.degrees(math.atan2(r-f['center'][1],z-f['center'][0]))
            delta=(a-f['start_deg'])%360 if f['sweep_deg']>0 else (f['start_deg']-a)%360
            t=delta/abs(f['sweep_deg'])
        else:
            dz,dr=f['end'][0]-f['start'][0],f['end'][1]-f['start'][1]
            denominator=dz*dz+dr*dr
            if denominator==0: continue
            t=((z-f['start'][0])*dz+(r-f['start'][1])*dr)/denominator
        if not -tolerance<=t<=1+tolerance: continue
        value,_=patch.evaluate(max(0,min(1,t)))
        if math.hypot(value[0]-z,value[1]-r)<=tolerance:
            from copy import deepcopy
            anchor=deepcopy(patch.anchor); anchor.t=max(0,min(1,t)); anchor.angle_deg=math.degrees(math.atan2(position[1],position[0]))%360
            return anchor
    return None
