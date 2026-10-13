"""Separate Rhino 8/GH Python 3 component. Phase 1 component remains unchanged.
Inputs (Item Access): Folder, ExportPath, PlacementPath (str); Edit, Save, Reload (bool).
Outputs: Cavities, Profiles, InterfaceAxes, InterfaceFrames, InstanceIDs,
InterfaceMetadata, Connectivity, Transforms, PlacementState, SelectedInstance,
CurrentPlacement, Status.
"""
import os
import sys
import json
import scriptcontext as sc
import Rhino
import Grasshopper as gh
from System import Object,Action
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

Cavities=DataTree[Object]();Profiles=DataTree[Object]();InterfaceAxes=DataTree[Object]()
InterfaceFrames=DataTree[Object]();InterfaceMetadata=DataTree[Object]();Transforms=DataTree[Object]()
InstanceIDs=[];Connectivity='';PlacementState='';SelectedInstance='';CurrentPlacement='';Status=''
try:
    folder=str(Folder)
    if not os.path.isdir(folder):raise ValueError('Folder must be the integrations/grasshopper directory')
    if folder not in sys.path:sys.path.insert(0,folder)
    import amcad_runtime as runtime
    from placement_controller import PlacementController,CommandEdges
    from placement_editor import PlacementEditor,show_editor
    from rhino_importer import import_model
    data=runtime.load_export(str(ExportPath));path=str(PlacementPath) if PlacementPath else None
    component=ghenv.Component;document=component.OnPingDocument()
    key=('amcad-phase2',str(document.DocumentID),str(component.InstanceGuid))
    runtime.require(bool(path),'Set a separate PlacementPath before using the controller')
    binding=(data['project']['id'],os.path.normcase(os.path.realpath(path)))
    session=sc.sticky.get(key)
    if session is not None and session['binding']!=binding:
        runtime.require(not session['model'].dirty and not (session.get('window') and session['window'].pending()),'Save or reload/discard the previous session before changing project/placement paths')
        old=session.get('window')
        if old is not None:Rhino.RhinoApp.InvokeOnUiThread(Action(old.Close))
        gh.Instances.DocumentServer.DocumentRemoved-=session['removed_handler']
        sc.sticky.pop(key,None);session=None
    if session is None:
        session={'binding':binding,'model':PlacementController(data,path,str(ExportPath)),
                 'window':None,'commands':CommandEdges(),'preview_key':None,'models':None}
        sc.sticky[key]=session
        def document_removed(sender,removed,owned_session=session,owned_key=key,owned_id=str(document.DocumentID)):
            doc=getattr(removed,'Document',removed)
            if str(getattr(doc,'DocumentID',''))!=owned_id:return
            window=owned_session.get('window')
            if window is not None:Rhino.RhinoApp.InvokeOnUiThread(Action(window.Close))
            sc.sticky.pop(owned_key,None)
            gh.Instances.DocumentServer.DocumentRemoved-=owned_session['removed_handler']
        session['removed_handler']=document_removed
        gh.Instances.DocumentServer.DocumentRemoved+=document_removed
    model=session['model'];model.refresh_export(data,str(ExportPath))
    def schedule():
        doc=component.OnPingDocument()
        if doc is None:return
        def expire(solution_doc):
            owner=component.OnPingDocument()
            if owner is not None and owner.DocumentID==solution_doc.DocumentID:component.ExpireSolution(False)
        doc.ScheduleSolution(1,gh.Kernel.GH_Document.GH_ScheduleDelegate(expire))
    def closed(window):
        if session.get('window') is window:session['window']=None
    def open_window():
        if session.get('window') is None:
            session['window']=PlacementEditor(model,schedule,closed);show_editor(session['window'])
        else:session['window'].BringToFront()
    # Momentary buttons are rising-edge commands, never actions on every solution.
    for name in session['commands'].consume({'Reload':Reload,'Save':Save,'Edit':Edit}):
        if name=='Reload':model.reload()
        elif name=='Save':model.save()
        else:Rhino.RhinoApp.InvokeOnUiThread(Action(open_window))
    window=session.get('window')
    if window is not None:Rhino.RhinoApp.InvokeOnUiThread(Action(window.sync))
    runtime.require(Rhino.RhinoDoc.ActiveDoc is not None and Rhino.RhinoDoc.ActiveDoc.ModelUnitSystem==Rhino.UnitSystem.Millimeters,'Set the Rhino document units to millimeters')
    preview_key=(model.version,Rhino.RhinoDoc.ActiveDoc.RuntimeSerialNumber)
    if session['preview_key']!=preview_key:
        session['models']=import_model(model.export_snapshot(),model.snapshot());session['preview_key']=preview_key
    for index,item in enumerate(session['models']):
        branch=GH_Path(index);InstanceIDs.append(item['instance_id'])
        Cavities.Add(item['geometry'],branch);Profiles.Add(item['profile'],branch)
        for axis in item['axes']:InterfaceAxes.Add(axis,branch)
        for frame in item['frames']:InterfaceFrames.Add(frame,branch)
        for interface in item['interfaces']:InterfaceMetadata.Add(json.dumps(interface),branch)
        for row in item['matrix']:
            for value in row:Transforms.Add(value,branch)
    PlacementState=json.dumps(model.snapshot(),indent=2);Connectivity=json.dumps(data['connectivity'],indent=2)
    record=next((r for r in model.parameters() if r['instance_id']==model.selected_id),None)
    if record:SelectedInstance=record['name'];CurrentPlacement=json.dumps(record,indent=2)
    Status='{} cavities · selected: {} · {}. Edit opens the six-field controller.'.format(len(InstanceIDs),SelectedInstance or 'none','UNSAVED placements' if model.dirty else 'saved placements')
except Exception as error:
    for tree in (Cavities,Profiles,InterfaceAxes,InterfaceFrames,InterfaceMetadata,Transforms):tree.Clear()
    InstanceIDs=[];Connectivity='';PlacementState='';SelectedInstance='';CurrentPlacement=''
    ghenv.Component.AddRuntimeMessage(gh.Kernel.GH_RuntimeMessageLevel.Error,str(error));Status='Placement controller failed: '+str(error)
