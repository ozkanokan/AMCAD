"""Optional OpenNURBS kernel check, outside Rhino; pip install rhino3dm==8.35.0."""
from pathlib import Path
import math
import rhino3dm as rg
import amcad_runtime as runtime
from rhino_importer import build_cavity,rhino_transform


def main():
    folder=Path(__file__).resolve().parent
    data=runtime.load_export(folder/'demo.grasshopper.json');stored=runtime.load_placements(folder/'demo.placements.json',data['project']['id'])
    definitions={c['id']:c for c in data['cavities']};geometry=[]
    for instance in data['instances']:
        cavity=definitions[instance['cavity_id']];brep,profile=build_cavity(cavity,rg)
        assert brep.IsValid and brep.IsSolid
        assert profile.SegmentCount==len(cavity['segments'])
        for index,piece in enumerate(cavity['segments']):
            curve=profile.SegmentCurve(index)
            if piece['kind']=='arc':
                arc=curve.TryGetArc();assert arc is not None and abs(arc.Radius-piece['radius'])<1e-8
                assert abs(abs(arc.AngleDegrees)-abs(piece['sweep_deg']))<1e-7
            else:assert curve.IsLinear()
        placement=stored['placements'][instance['id']];transform=rhino_transform(placement,rg)
        origin=profile.PointAtStart;expected=runtime.transform_point(runtime.matrix(placement),(origin.X,origin.Y,origin.Z))
        assert brep.Transform(transform) and profile.Transform(transform)
        actual=profile.PointAtStart;assert runtime.close((actual.X,actual.Y,actual.Z),expected)
        assert brep.IsValid and brep.IsSolid;geometry.append(brep)
        print(instance['name']+': exact profile, circular fillet, chamfer and transformed closed Brep PASS')
    assert len(geometry)==2 and geometry[0] is not geometry[1]
    a,b=[g.GetBoundingBox() for g in geometry];assert a.Max.X<b.Min.X
    print('Independent placements and disjoint demo bounds PASS (rhino3dm '+rg.__version__+')')


if __name__=='__main__':main()
