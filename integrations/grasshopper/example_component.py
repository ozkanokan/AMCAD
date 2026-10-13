"""Paste into a Rhino 8 Grasshopper Python 3 Script component; see README.md."""
# Inputs: Folder, ExportPath, PlacementPath, IDs, X, Y, Z, Rx, Ry, Rz,
#         SavePlacements, Reload. Numeric inputs and IDs use List Access.
# Outputs: Cavities, Profiles, InterfaceAxes, InterfaceFrames, InstanceIDs,
#          InterfaceMetadata, Connectivity, Transforms, Status.
import sys
import os
import json
import importlib
import Grasshopper as gh
from System import Object
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

Cavities=DataTree[Object]();Profiles=DataTree[Object]();InterfaceAxes=DataTree[Object]()
InterfaceFrames=DataTree[Object]();InterfaceMetadata=DataTree[Object]();Transforms=DataTree[Object]()
InstanceIDs=[];Connectivity='';Status=''
try:
    folder=str(Folder)
    if not os.path.isdir(folder):raise ValueError('Folder must be the integrations/grasshopper directory')
    if folder not in sys.path:sys.path.insert(0,folder)
    import amcad_runtime
    import rhino_importer
    if Reload:importlib.reload(amcad_runtime);importlib.reload(rhino_importer)
    data=amcad_runtime.load_export(str(ExportPath))
    placement_path=str(PlacementPath) if PlacementPath else None
    stored=amcad_runtime.reconcile_placements(data,amcad_runtime.load_placements(placement_path,data['project']['id']))
    def values(value):
        if value is None:return []
        if isinstance(value,(str,int,float)):return [value]
        return list(value)
    ids=values(IDs);overrides={key:values(value) for key,value in [('X',X),('Y',Y),('Z',Z),('Rx',Rx),('Ry',Ry),('Rz',Rz)]}
    amcad_runtime.apply_parameters(data,stored,ids,overrides)
    models=rhino_importer.import_model(data,stored)
    if SavePlacements:
        if not placement_path:raise ValueError('Choose a separate PlacementPath before saving')
        amcad_runtime.save_placements(placement_path,stored,str(ExportPath))
    for index,model in enumerate(models):
        path=GH_Path(index);InstanceIDs.append(model['instance_id'])
        Cavities.Add(model['geometry'],path);Profiles.Add(model['profile'],path)
        for axis in model['axes']:InterfaceAxes.Add(axis,path)
        for frame in model['frames']:InterfaceFrames.Add(frame,path)
        for interface in model['interfaces']:InterfaceMetadata.Add(json.dumps(interface),path)
        for row in model['matrix']:
            for value in row:Transforms.Add(value,path)
    Connectivity=json.dumps(data['connectivity'],indent=2)
    Status='Imported {} independent cavities in mm; {} unassigned schematic instances retained as connectivity boundaries.'.format(len(models),len(data['excluded_instances']))
except Exception as error:
    for tree in (Cavities,Profiles,InterfaceAxes,InterfaceFrames,InterfaceMetadata,Transforms):tree.Clear()
    InstanceIDs=[];Connectivity=''
    ghenv.Component.AddRuntimeMessage(gh.Kernel.GH_RuntimeMessageLevel.Error,str(error))
    Status='AMCAD import failed: '+str(error)
