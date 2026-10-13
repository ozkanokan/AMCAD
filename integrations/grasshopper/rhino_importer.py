"""RhinoCommon exact geometry adapter for Rhino 8 Python 3 (CPython 3.9+)."""
import math
try:
    from . import amcad_runtime as runtime
except ImportError:
    import amcad_runtime as runtime


def build_profile(cavity,rg):
    """Map AMCAD (axial Z, radial Y) to local (radial, 0, axial)."""
    curve=rg.PolyCurve()
    def point(value):return rg.Point3d(value[1],0,value[0])
    for piece in cavity['segments']:
        if piece['kind']=='line':segment=rg.LineCurve(point(piece['start']),point(piece['end']))
        elif piece['kind']=='arc':
            a=math.radians(piece['start_deg']+piece['sweep_deg']/2)
            center=piece['center'];middle=(center[0]+piece['radius']*math.cos(a),center[1]+piece['radius']*math.sin(a))
            arc=rg.Arc(point(piece['start']),point(middle),point(piece['end']))
            runtime.require(arc.IsValid,'Rhino rejected fillet arc in '+cavity['name'])
            segment=arc.ToNurbsCurve()
        else:raise runtime.ImportErrorDetail('Unsupported profile segment: '+piece['kind'])
        runtime.require(curve.Append(segment),'Rhino could not join exact profile segments')
    runtime.require(curve.IsValid,'Rhino rejected cavity profile '+cavity['name'])
    return curve


def build_cavity(cavity,rg):
    profile=build_profile(cavity,rg)
    axis=rg.Line(rg.Point3d(0,0,0),rg.Point3d(0,0,1))
    surface=rg.RevSurface.Create(profile.ToNurbsCurve(),axis,0,2*math.pi)
    runtime.require(surface is not None,'Rhino cannot revolve this profile: '+cavity['name'])
    brep=rg.Brep.CreateFromRevSurface(surface,True,True)
    runtime.require(brep is not None and brep.IsValid and brep.IsSolid,'Rhino cannot create a valid closed cavity: '+cavity['name'])
    return brep,profile


def rhino_transform(placement,rg):
    result=rg.Transform.Identity
    if callable(result):result=result()  # OpenNURBS test backend exposes a static method.
    for i,row in enumerate(runtime.matrix(placement)):
        for j,value in enumerate(row):setattr(result,"M{}{}".format(i,j),value)
    return result


def import_model(export,placements,axis_length_mm=10):
    """Return independent world Breps/curves/interfaces keyed by stable instance ID."""
    import Rhino
    import Rhino.Geometry as rg
    runtime.validate_export(export)
    runtime.require(Rhino.RhinoDoc.ActiveDoc is not None and Rhino.RhinoDoc.ActiveDoc.ModelUnitSystem==Rhino.UnitSystem.Millimeters,'Set the Rhino document units to millimeters before importing')
    runtime.require(runtime.number(axis_length_mm,'Axis length')>0,'Interface axis length must be positive')
    placements=runtime.reconcile_placements(export,placements)
    definitions={c['id']:c for c in export['cavities']};result=[]
    # Build once per definition, then explicitly duplicate for each physical instance.
    local={key:build_cavity(cavity,rg) for key,cavity in definitions.items()}
    for instance in sorted(export['instances'],key=lambda item:item['id']):
        placement=placements['placements'][instance['id']];transform=rhino_transform(placement,rg)
        brep,profile=local[instance['cavity_id']];brep=brep.DuplicateBrep();profile=profile.DuplicateCurve()
        if brep.SolidOrientation==rg.BrepSolidOrientation.Inward:brep.Flip()
        runtime.require(brep.Transform(transform) and profile.Transform(transform),'Rhino rejected instance transform')
        for geometry in (brep,profile):
            geometry.SetUserString('amcad.instance_id',instance['id'])
            geometry.SetUserString('amcad.cavity_id',instance['cavity_id'])
            geometry.SetUserString('amcad.cavity_revision',str(instance['cavity_revision']))
        interfaces=runtime.world_interfaces(definitions[instance['cavity_id']],instance['id'],placement)
        axes=[];frames=[]
        for interface in interfaces:
            position=rg.Point3d(*interface['position_mm']);direction=rg.Vector3d(*interface['direction'])
            axes.append(rg.Line(position,position+direction*axis_length_mm))
            frames.append(rg.Plane(position,rg.Vector3d(*interface['section_u']),rg.Vector3d(*interface['section_v'])))
        result.append({'instance_id':instance['id'],'name':instance['name'],'geometry':brep,'profile':profile,
            'interfaces':interfaces,'axes':axes,'frames':frames,'matrix':runtime.matrix(placement)})
    return result
