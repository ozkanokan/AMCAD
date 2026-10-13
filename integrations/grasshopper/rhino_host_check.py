"""Open/run in Rhino 8 ScriptEditor Python 3 with a blank millimeter document."""
import sys
from pathlib import Path
folder=Path(__file__).resolve().parent
if str(folder) not in sys.path:sys.path.insert(0,str(folder))
import amcad_runtime as runtime
from rhino_importer import import_model

data=runtime.load_export(folder/'demo.grasshopper.json')
stored=runtime.load_placements(folder/'demo.placements.json',data['project']['id'])
models=import_model(data,stored)
assert len(models)==2 and models[0]['geometry'] is not models[1]['geometry']
for model in models:
    assert model['geometry'].IsValid and model['geometry'].IsSolid
    assert model['geometry'].GetUserString('amcad.instance_id')==model['instance_id']
    for metadata,axis,frame in zip(model['interfaces'],model['axes'],model['frames']):
        assert runtime.close((axis.From.X,axis.From.Y,axis.From.Z),metadata['position_mm'])
        assert runtime.close((frame.Origin.X,frame.Origin.Y,frame.Origin.Z),metadata['position_mm'])
        assert runtime.close((frame.ZAxis.X,frame.ZAxis.Y,frame.ZAxis.Z),metadata['direction'])
    print(model['name']+': RhinoCommon solid, instance tags and interface transforms PASS')
print('Native Rhino 8 Phase 1 self-test PASS; no objects or user library files were modified.')
