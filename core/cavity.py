"""Parametric axial Z/radial Y geometry in mm (persisted as z/r for compatibility)."""
from copy import deepcopy
from dataclasses import dataclass, field, asdict
import math
from core.port import new_id
from core.cavity_surface import SurfaceAnchor, ChannelSection, normalized, finite_number, resolve_anchor

EPS = 1e-9


def finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{label} must be finite')
    return value


@dataclass
class Corner:
    type: str = 'SHARP'
    radius_mm: float | None = None
    length_mm: float | None = None
    angle_deg: float | None = None

    def validate(self):
        """A corner has exactly one feature, including when read from old files."""
        if self.type == 'SHARP':
            if any(v is not None for v in (self.radius_mm, self.length_mm, self.angle_deg)):
                raise ValueError('SHARP must not contain fillet/chamfer parameters')
        elif self.type == 'FILLET':
            if self.length_mm is not None or self.angle_deg is not None:
                raise ValueError('Fillet contains chamfer parameters')
            if finite(self.radius_mm, 'Fillet radius') <= 0:
                raise ValueError('Fillet radius must be positive')
        elif self.type == 'CHAMFER':
            if self.radius_mm is not None:
                raise ValueError('Chamfer contains a fillet radius')
            if finite(self.length_mm, 'Chamfer length') <= 0:
                raise ValueError('Chamfer length must be positive')
            if not 0 < finite(self.angle_deg, 'Chamfer angle') < 180:
                raise ValueError('Chamfer angle must be between 0 and 180 degrees')
        else:
            raise ValueError('Unknown corner type')
        return self


@dataclass
class ProfileVertex:
    z: float
    r: float
    id: str = field(default_factory=new_id)
    corner: Corner = field(default_factory=Corner)


@dataclass
class HydraulicInterface:
    hydraulic_port_id: str
    interface_type: str = 'AXIAL'
    z_mm: float = 0
    r_mm: float | None = 0
    nominal_connection_diameter_mm: float = 4
    preferred_direction: str = 'UNSPECIFIED'
    id: str = field(default_factory=new_id)
    surface_anchor: SurfaceAnchor | None = None
    direction: tuple | None = None
    section: ChannelSection | None = None
    section_rotation_deg: float = 0
    preview_length_mm: float = 2
    preview_mode: str = 'CENTERED'

    def __post_init__(self):
        if self.direction is not None:
            unit = normalized(self.direction)
            self.direction = tuple(self.direction) if abs(math.hypot(*self.direction)-1)<1e-12 else unit

    @classmethod
    def from_dict(cls, data):
        data = deepcopy(data)
        # Missing fields in older files retain the historical one-sided 10 mm preview.
        data.setdefault('preview_length_mm',10)
        data.setdefault('preview_mode','FORWARD')
        if data.get('surface_anchor') is not None:
            data['surface_anchor'] = SurfaceAnchor(**data['surface_anchor'])
        if data.get('section') is not None:
            data['section'] = ChannelSection(**data['section'])
        if data.get('direction') is not None:
            data['direction'] = tuple(data['direction'])
        return cls(**data)

    def validate(self, port_ids):
        if self.hydraulic_port_id not in port_ids:
            raise ValueError('Interface references an unknown schematic port ID')
        if self.interface_type not in ('AXIAL','RADIAL','SURFACE'):
            raise ValueError('Interface type must be AXIAL, RADIAL or SURFACE')
        if self.interface_type=='SURFACE' and self.surface_anchor is None:
            raise ValueError('Surface interface needs an anchor')
        if self.surface_anchor is not None: self.surface_anchor.validate()
        if self.direction is not None:
            unit=normalized(self.direction)
            if abs(math.hypot(*self.direction)-1)>1e-12: self.direction=unit
        if self.section is not None: self.section.validate()
        if self.preview_mode not in ('CENTERED','FORWARD'): raise ValueError('Unknown preview mode')
        finite_number(self.section_rotation_deg,'Section rotation')
        if finite_number(self.preview_length_mm,'Preview length')<=0:
            raise ValueError('Preview length must be positive')
        if self.preferred_direction not in ('AXIAL_POSITIVE','AXIAL_NEGATIVE','RADIAL','UNSPECIFIED'):
            raise ValueError('Invalid preferred routing direction')
        finite(self.z_mm,'Interface Z')
        if self.r_mm is not None and finite(self.r_mm,'Interface Y') < 0:
            raise ValueError('Interface Y cannot be negative')
        if finite(self.nominal_connection_diameter_mm,'Connection diameter') <= 0:
            raise ValueError('Connection diameter must be positive')
        if not isinstance(self.id,str) or not self.id:
            raise ValueError('Interface needs a persistent ID')
        return self


def point(v):
    return (v.z,v.r)


def distance(a,b):
    return math.hypot(a[0]-b[0],a[1]-b[1])


def intersection(a,b,c,d):
    def cross(p,q,r): return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    def on(p,q,r):
        return abs(cross(p,q,r))<EPS and min(p[0],q[0])-EPS<=r[0]<=max(p[0],q[0])+EPS and min(p[1],q[1])-EPS<=r[1]<=max(p[1],q[1])+EPS
    ab1,ab2,cd1,cd2=cross(a,b,c),cross(a,b,d),cross(c,d,a),cross(c,d,b)
    return (ab1*ab2 < -EPS and cd1*cd2 < -EPS) or any((on(a,b,c),on(a,b,d),on(c,d,a),on(c,d,b)))


@dataclass
class CavityProfile:
    vertices: list[ProfileVertex] = field(default_factory=list)
    id: str = field(default_factory=new_id)
    schema_version: int = 1
    units: str = 'mm'
    datum: dict = field(default_factory=lambda:{'mounting_face_z_mm':0,'positive_z':'DEPTH_INTO_MANIFOLD','revolve_axis_r_mm':0})

    @classmethod
    def from_dict(cls,data):
        data=deepcopy(data)
        data['vertices']=[ProfileVertex(**{**v,'corner':Corner(**v.get('corner',{}))}) for v in data['vertices']]
        return cls(**data)

    def to_dict(self): return asdict(self)

    def vertex(self,vertex_id):
        return next(v for v in self.vertices if v.id==vertex_id)

    def add_point(self,z,r,after_id=None):
        finite(z,'Z'); finite(r,'Y')
        if r<0: raise ValueError('Y cannot be negative')
        vertex=ProfileVertex(z,r)
        index=len(self.vertices) if after_id is None else next(i for i,v in enumerate(self.vertices) if v.id==after_id)+1
        self.vertices.insert(index,vertex)
        try:
            # Only insert the new theoretical vertex; existing IDs/features stay intact.
            if any(v.corner.type!='SHARP' for v in self.vertices): self.features()
        except ValueError:
            del self.vertices[index]
            raise
        return vertex

    def edit_point(self,vertex_id,z,r):
        """Edit only the theoretical control point; recompute features, never retune them."""
        finite(z,'Z'); finite(r,'Y')
        if r<0: raise ValueError('Y cannot be negative')
        v=self.vertex(vertex_id); before=(v.z,v.r)
        v.z,v.r=z,r
        try:
            # A point edit must not invalidate an already installed corner feature.
            if any(p.corner.type!='SHARP' for p in self.vertices): self.features()
        except ValueError:
            v.z,v.r=before
            raise

    def delete_point(self,vertex_id):
        index=next(i for i,v in enumerate(self.vertices) if v.id==vertex_id)
        candidate=deepcopy(self); del candidate.vertices[index]
        for i,v in enumerate(candidate.vertices):
            if i in (0,len(candidate.vertices)-1) and v.corner.type!='SHARP' and not candidate.axis_closed():
                raise ValueError('Return the adjacent corner to SHARP before deleting its supporting point')
        if any(v.corner.type!='SHARP' for v in candidate.vertices): candidate.features()
        del self.vertices[index]

    def set_corner(self,vertex_id,corner):
        """Associate one parametric feature with a vertex without changing its ID/position."""
        corner.validate()
        candidate=deepcopy(self); candidate.vertex(vertex_id).corner=deepcopy(corner)
        if corner.type!='SHARP': candidate.validate()
        self.vertex(vertex_id).corner=deepcopy(corner)

    def axis_closed(self):
        return len(self.vertices)>=3 and self.vertices[0].r==0 and self.vertices[-1].r==0

    def features(self):
        """Exact tangent points/arc centers; vertices remain authoritative."""
        features=[]
        for i,v in enumerate(self.vertices):
            p=point(v); corner=v.corner
            corner.validate()
            if corner.type=='SHARP':
                features.append({'kind':'sharp','entry':p,'exit':p,'setback_in':0,'setback_out':0}); continue
            if (i==0 or i==len(self.vertices)-1) and not self.axis_closed():
                raise ValueError('Endpoint treatment needs adjacent geometry from two axis endpoints and a virtual closure edge')
            a,b=point(self.vertices[(i-1)%len(self.vertices)]),point(self.vertices[(i+1)%len(self.vertices)])
            la,lb=distance(a,p),distance(b,p)
            if min(la,lb)<=EPS: raise ValueError('Corner has a zero-length adjacent segment')
            u=((a[0]-p[0])/la,(a[1]-p[1])/la); w=((b[0]-p[0])/lb,(b[1]-p[1])/lb)
            theta=math.acos(max(-1,min(1,u[0]*w[0]+u[1]*w[1])))
            if theta<EPS or math.pi-theta<EPS: raise ValueError('Corner needs a genuine non-collinear bend')
            if corner.type=='FILLET':
                radius=corner.radius_mm
                da=db=radius/math.tan(theta/2)
            else:
                da=corner.length_mm; angle=corner.angle_deg
                if not 0<angle<180-math.degrees(theta): raise ValueError('Chamfer angle is incompatible with the included corner angle')
                alpha=math.radians(angle); db=da*math.sin(alpha)/math.sin(theta+alpha)
            if da>=la-EPS or db>=lb-EPS: raise ValueError('Corner treatment is too large for its adjacent segments')
            entry=(p[0]+u[0]*da,p[1]+u[1]*da); exit=(p[0]+w[0]*db,p[1]+w[1]*db)
            feature={'kind':'arc' if corner.type=='FILLET' else 'chamfer','entry':entry,'exit':exit,
                     'setback_in':da,'setback_out':db}
            if corner.type=='FILLET':
                bisector=(u[0]+w[0],u[1]+w[1]); norm=math.hypot(*bisector)
                length=radius/math.sin(theta/2)
                center=(p[0]+bisector[0]/norm*length,p[1]+bisector[1]/norm*length)
                start=math.degrees(math.atan2(entry[1]-center[1],entry[0]-center[0]))
                turn=-(u[0]*w[1]-u[1]*w[0]); sweep=math.copysign(180-math.degrees(theta),turn)
                feature.update(center=center,radius=radius,start_deg=start,sweep_deg=sweep)
                minimum=min(entry[1],exit[1])
                delta=(270-start)%360 if sweep>0 else (start-270)%360
                if delta<=abs(sweep)+EPS: minimum=min(minimum,center[1]-radius)
                if minimum < -EPS: raise ValueError('Fillet would cross the Y=0 revolve axis')
            features.append(feature)
        for i in range(len(self.vertices)-1):
            if features[i]['setback_out']+features[i+1]['setback_in']>=distance(point(self.vertices[i]),point(self.vertices[i+1]))-EPS:
                raise ValueError('Adjacent corner treatments overlap or consume a segment')
        if self.axis_closed():
            if features[-1]['setback_out']+features[0]['setback_in']>=distance(point(self.vertices[-1]),point(self.vertices[0]))-EPS:
                raise ValueError('Endpoint treatments overlap on the virtual closure edge')
        return features

    def pieces(self):
        features=self.features(); pieces=[]
        if not features: return pieces
        first=features[0]
        if first['kind']=='arc': pieces.append(first)
        elif first['kind']=='chamfer': pieces.append({'kind':'line','start':first['entry'],'end':first['exit']})
        current=first['exit']
        for feature in features[1:]:
            pieces.append({'kind':'line','start':current,'end':feature['entry']})
            if feature['kind']=='arc': pieces.append(feature)
            elif feature['kind']=='chamfer': pieces.append({'kind':'line','start':feature['entry'],'end':feature['exit']})
            current=feature['exit']
        return pieces

    def display_points(self):
        """Transient tessellation for validation, never saved as profile vertices."""
        result=[]
        for piece in self.pieces():
            if piece['kind']=='line': points=[piece['start'],piece['end']]
            else:
                points=[]
                for i in range(33):
                    angle=math.radians(piece['start_deg']+piece['sweep_deg']*i/32)
                    points.append((piece['center'][0]+piece['radius']*math.cos(angle),piece['center'][1]+piece['radius']*math.sin(angle)))
            for p in points:
                if not result or distance(result[-1],p)>EPS: result.append(p)
        return result

    def validation_errors(self, revolved=False):
        try:
            if self.schema_version!=1 or self.units!='mm': raise ValueError('Unsupported cavity profile version or units')
            if self.datum!={'mounting_face_z_mm':0,'positive_z':'DEPTH_INTO_MANIFOLD','revolve_axis_r_mm':0}:
                raise ValueError('Cavity datum must be Z=0 mounting face, positive Z depth, Y=0 axis')
            if not isinstance(self.id,str) or not self.id: raise ValueError('Profile needs a persistent ID')
            ids=[v.id for v in self.vertices]
            if len(ids)!=len(set(ids)) or any(not isinstance(i,str) or not i for i in ids): raise ValueError('Vertex IDs must be unique and nonempty')
            for v in self.vertices:
                finite(v.z,'Z'); finite(v.r,'Y')
                if v.r<0: raise ValueError('Y cannot be negative')
            if len(self.vertices)<2: raise ValueError('At least two profile points are required')
            if revolved:
                if self.vertices[0].r!=0 or self.vertices[-1].r!=0:
                    raise ValueError('REVOLVED_PROFILE first and last Y must be zero; explicitly correct legacy endpoints')
                if len(self.vertices)<3: raise ValueError('A finished cavity needs at least three theoretical vertices')
            raw=[point(v) for v in self.vertices]
            if any(distance(a,b)<=EPS for a,b in zip(raw,raw[1:])): raise ValueError('Coincident points / zero-length segment')
            for a,b,c in zip(raw,raw[1:],raw[2:]):
                u=(a[0]-b[0],a[1]-b[1]); w=(c[0]-b[0],c[1]-b[1])
                if abs(u[0]*w[1]-u[1]*w[0])<=EPS and u[0]*w[0]+u[1]*w[1]>0:
                    raise ValueError('Profile retraces an adjacent segment')
            # Axial profile is open. Non-adjacent touches count as self-intersection.
            for i in range(len(raw)-1):
                for j in range(i+2,len(raw)-1):
                    if intersection(raw[i],raw[i+1],raw[j],raw[j+1]): raise ValueError('Profile has a self-intersection')
            displayed=self.display_points()
            for i in range(len(displayed)-1):
                for j in range(i+2,len(displayed)-1):
                    if intersection(displayed[i],displayed[i+1],displayed[j],displayed[j+1]):
                        raise ValueError('Treated profile has a self-intersection')
            if revolved or self.axis_closed():
                # Virtual closure is used only for validation; it is not a wall surface.
                if distance(displayed[0],displayed[-1])<=EPS:
                    raise ValueError('Degenerate virtual closure boundary')
                if abs(displayed[0][1])>EPS or abs(displayed[-1][1])>EPS:
                    raise ValueError('Evaluated endpoints must meet the revolve axis')
                if any(y<=EPS for _,y in displayed[1:-1]):
                    raise ValueError('Profile touches or overlaps the virtual closure axis')
                for a,b in zip(displayed[1:-2],displayed[2:-1]):
                    if intersection(a,b,displayed[-1],displayed[0]):
                        raise ValueError('Profile intersects the virtual closure edge')
                area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(displayed,displayed[1:]+displayed[:1]))/2
                if abs(area)<=EPS: raise ValueError('Cavity must enclose a nonzero cross-sectional area')
            return []
        except (ValueError,TypeError) as error: return [str(error)]

    def validate(self, revolved=False):
        errors=self.validation_errors(revolved=revolved)
        if errors: raise ValueError(errors[0])
        return self


def snapped(z,r,increment):
    finite(z,'Z'); finite(r,'Y')
    if increment not in (0,.1,.5,1): raise ValueError('Unsupported grid snap')
    if increment:
        z=round(round(z/increment)*increment,10); r=round(round(r/increment)*increment,10)
    return z,max(0,r)


@dataclass
class PhysicalDefinition:
    cavity_type: str = 'NONE'
    cavity_profile: CavityProfile | None = None
    hydraulic_interfaces: list[HydraulicInterface] = field(default_factory=list)

    @classmethod
    def from_dict(cls,data):
        data=deepcopy(data)
        if data.get('cavity_profile') is not None: data['cavity_profile']=CavityProfile.from_dict(data['cavity_profile'])
        data['hydraulic_interfaces']=[HydraulicInterface.from_dict(i) for i in data.get('hydraulic_interfaces',[])]
        return cls(**data)

    def validate(self,ports,strict=False):
        """Strict finished-cavity checks; default permits unchanged legacy project data."""
        if self.cavity_type=='NONE':
            if self.cavity_profile is not None or self.hydraulic_interfaces: raise ValueError('NONE cavity must not contain profile/interfaces')
            return self
        if self.cavity_type!='REVOLVED_PROFILE' or self.cavity_profile is None: raise ValueError('Invalid cavity type/profile')
        self.cavity_profile.validate(revolved=strict)
        mapped=set(); ids=set()
        for interface in self.hydraulic_interfaces:
            interface.validate({p.id for p in ports})
            if interface.hydraulic_port_id in mapped: raise ValueError('Duplicate physical mapping for one schematic port')
            if interface.id in ids: raise ValueError('Duplicate interface ID')
            mapped.add(interface.hydraulic_port_id); ids.add(interface.id)
        return self

    def warnings(self,ports):
        if self.cavity_type=='NONE': return []
        mapped={i.hydraulic_port_id for i in self.hydraulic_interfaces}
        warnings=[f'Required port {p.id} has no physical interface' for p in ports if p.required and p.id not in mapped]
        for interface in self.hydraulic_interfaces:
            if interface.surface_anchor is not None:
                try: resolve_anchor(self.cavity_profile,interface.surface_anchor)
                except ValueError as error: warnings.append(f'Port {interface.hydraulic_port_id}: INVALID anchor — {error}')
        return warnings
