"""Simple Eto topology editor with a static SVG overview and Save-only publication."""
import math
import traceback
from copy import deepcopy
import Eto.Forms as ef
import Eto.Drawing as ed
from System import Array, String
from System.Drawing import Color
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
try:
    from .topology_core import Draft, make_port, bind_port, key
    from . import topology_overview as overview
    from .topology_diagnostics import checkpoint
except ImportError:
    from topology_core import Draft, make_port, bind_port, key
    import topology_overview as overview
    from topology_diagnostics import checkpoint


def control(kind, text):
    value=kind();value.Text=str(text);return value


class PortHighlight(rd.DisplayConduit):
    def __init__(self):
        super().__init__(); self.ports = []; self.cavity = None

    def DrawForeground(self, event):
        if self.cavity is not None:
            for edge in self.cavity.Edges: event.Display.DrawCurve(edge, Color.Orange, 3)
        for p in self.ports:
            point = rg.Point3d(*p['position_mm']); direction = rg.Vector3d(*p['direction'])
            event.Display.DrawDot(point, p.get('label', p['id']), Color.Black, Color.Yellow)
            event.Display.DrawArrow(rg.Line(point, point+direction*6), Color.OrangeRed, 2, .8)


def redraw():
    if Rhino.RhinoDoc.ActiveDoc is not None: Rhino.RhinoDoc.ActiveDoc.Views.Redraw()


def nearest_surface(brep, value):
    """Find an actual trimmed face, not a guessed point from existing interfaces."""
    point = rg.Point3d(*value); best = None
    for face in brep.Faces:
        ok,u,v = face.ClosestPoint(point)
        if not ok or face.IsPointOnFace(u,v) == rg.PointFaceRelation.Exterior: continue
        q = face.PointAt(u,v); normal = face.NormalAt(u,v)
        if face.OrientationIsReversed: normal.Reverse()
        if not normal.Unitize(): continue
        gap = point.DistanceTo(q)
        if best is None or gap < best[0]: best = (gap,q,normal)
    if best is None: raise ValueError('No usable trimmed cavity face at this location')
    return best


class PhysicalPortDialog:
    def __init__(self, editor, iid):
        self.editor=editor;self.iid=iid;self.result=None;self.created_ref=None;self._events=[]
        self._click_count=0;self._submitting=False
        self.form=ef.Dialog();self.form.Title='Add Physical Port — Create Port v2'
        self.form.ClientSize=ed.Size(540,760);self.form.MinimumSize=ed.Size(500,720);self.form.Resizable=True
        layout=ef.DynamicLayout();layout.Padding=ed.Padding(12);layout.Spacing=ed.Size(7,5)
        self.fields={};initial=next(p for r,p in editor.draft.all_ports().items() if r[0]==iid)
        values=[('Name','New port')]+list(zip(('X','Y','Z'),initial['position_mm']))+list(zip(('Dx','Dy','Dz'),initial['direction']))
        values += [('Diameter',4),('Width',4),('Height',8),('Section rotation (deg)',0)]
        for name,value in values:
            field=control(ef.TextBox,format(value,'.17g') if isinstance(value,(int,float)) else value)
            field.Width=260
            label=control(ef.Label,name);label.Width=185
            self.fields[name]=field;layout.AddRow(label,field)
        self.shape=ef.DropDown();self.shape.Width=260;self.shape.DataStore=Array[String](['CIRCLE','RECTANGLE','SLOT']);self.shape.SelectedIndex=0
        layout.AddRow(control(ef.Label,'Section'),self.shape)
        self.references=[p for r,p in editor.draft.base.items() if r[0]==iid]
        self.reference=ef.DropDown();self.reference.Width=260;self.reference.DataStore=Array[String]([editor.names.get(key(p),p.get('label',p['id'])) for p in self.references]);self.reference.SelectedIndex=0
        layout.AddRow(control(ef.Label,'Internal source interface'),self.reference)
        self.message=control(ef.Label,'Pick near the cavity to project onto its surface. SLOT uses overall Width along U / Height along V. Confirm the new opening reaches the selected internal volume.')
        self.message.Wrap=ef.WrapMode.Word;self.message.Width=450
        self.error_label=control(ef.Label,'')
        self.error_label.Wrap=ef.WrapMode.Word;self.error_label.Height=100
        self.error_label.TextColor=ed.Color.FromArgb(170,0,0,255)
        self.error_label.BackgroundColor=ed.Color.FromArgb(255,240,240,255)
        self.progress=control(ef.Label,'Ready. Create Port progress and errors are shown here and in Rhino F2 history.')
        self.progress.Wrap=ef.WrapMode.Word
        actions=ef.DynamicLayout();actions.Spacing=ed.Size(7,5)
        for text,action in [('Pick surface position',self.pick_position),('Pick direction',self.pick_direction),('Create port',self.submit)]:
            button=control(ef.Button,text);button.Click+=action;self._events.append((button,action));actions.AddRow(button)
            if action==self.submit:self.create_button=button
        # Keep errors and action buttons visible even when numeric fields need
        # scrolling; the old single long layout could hide validation messages.
        # Keep explanatory text out of the two-column field grid: a long label
        # in that grid can force the label column beyond the visible viewport.
        fields=ef.DynamicLayout();fields.Spacing=ed.Size(6,6)
        fields.AddRow(layout);fields.AddRow(self.message);fields.AddRow(None)
        scroll=ef.Scrollable();scroll.Content=fields
        root=ef.TableLayout();root.Padding=ed.Padding(10);root.Spacing=ed.Size(6,6)
        for widget,stretch in ((self.progress,False),(self.error_label,False),(scroll,True),(actions,False)):
            row=ef.TableRow();row.Cells.Add(ef.TableCell(widget,True));row.ScaleHeight=stretch;root.Rows.Add(row)
        self.form.Content=root
        self.trace('Create Port click handler registered; cavity='+iid)

    def dispose(self):
        for button,handler in self._events:button.Click-=handler
        self._events=[];self.form.Dispose()

    def number(self,name):
        try:return float(self.fields[name].Text.strip())
        except (ValueError,TypeError) as error:raise ValueError('Invalid '+name+' value; use a number with a decimal period') from error

    def vector(self,names):return [self.number(n) for n in names]

    def trace(self,message):
        Rhino.RhinoApp.WriteLine('[AMCAD Create Port] '+str(message))
        self.progress.Text=str(message)

    def report_error(self,stage,error):
        detail=stage+': '+type(error).__name__+': '+str(error)
        outcome='Nothing was added. Correct the values and retry.' if self.created_ref is None else 'The port is already in the draft. Close this dialog; do not create it again.'
        Rhino.RhinoApp.WriteLine('[AMCAD Create Port] FAILED '+detail)
        Rhino.RhinoApp.WriteLine(traceback.format_exc())
        self.error_label.Text='ERROR — '+detail+'\n'+outcome
        self.progress.Text='FAILED '+detail

    def picked(self,prompt,base=None,surface=False):
        from time import perf_counter
        result=[None]
        started=perf_counter();entered=[False];failure=[None];stage=['callback entry'];kind='surface' if surface else 'direction'
        self.trace('{} pick requested; InvokeRequired={}; dialog Visible={}'.format(kind,getattr(Rhino.RhinoApp,'InvokeRequired','unavailable'),getattr(self.form,'Visible','unavailable')))
        def run_pick(*args):
            entered[0]=True
            self.trace('{} pick callback entered after {:.3f}s; InvokeRequired={}'.format(kind,perf_counter()-started,getattr(Rhino.RhinoApp,'InvokeRequired','unavailable')))
            if getattr(Rhino.RhinoApp,'InvokeRequired',False) is True:
                raise RuntimeError('Rhino pick callback is not on the UI thread; no getter started')
            stage[0]='create preview and resolve host';self.trace(kind+' '+stage[0]+' START')
            preview=PortHighlight();preview.cavity=self.editor.host(self.iid)
            preview.ports=[p for ref,p in self.editor.draft.all_ports().items() if ref[0]==self.iid]
            def candidate(sender,event):
                try:
                    _,q,n=nearest_surface(preview.cavity,(event.CurrentPoint.X,event.CurrentPoint.Y,event.CurrentPoint.Z))
                    event.Display.DrawDot(q,'New opening',Color.Black,Color.Yellow)
                    event.Display.DrawArrow(rg.Line(q,q+n*6),Color.OrangeRed,2,.8)
                except Exception as error:
                    self.trace('Surface preview: '+str(error))
            stage[0]='create GetPoint';self.trace(kind+' '+stage[0]+' START')
            getter=Rhino.Input.Custom.GetPoint();attached=False
            try:
                stage[0]='set command prompt';getter.SetCommandPrompt(prompt)
                if surface:
                    # RhinoCommon Brep overload requires all FOUR arguments.
                    # False rejects off-object picks; face index -1 covers all faces.
                    stage[0]='Constrain(Brep, -1, -1, False)';self.trace(kind+' '+stage[0]+' START')
                    constrained=getter.Constrain(preview.cavity,-1,-1,False)
                    self.trace('Brep constraint result={!r}; faces={}'.format(constrained,getattr(getattr(preview.cavity,'Faces',None),'Count','unknown')))
                    if not constrained:raise ValueError('Rhino rejected the cavity Brep constraint; point getter was not started')
                    stage[0]='attach candidate preview';getter.DynamicDraw+=candidate;attached=True
                stage[0]='configure base point and display'
                if base is not None:getter.SetBasePoint(rg.Point3d(*base),True);getter.DrawLineFromPoint(rg.Point3d(*base),True)
                preview.Enabled=True;redraw()
                if surface:
                    stage[0]='focus Rhino';Rhino.RhinoApp.SetFocusToMainWindow()
                stage[0]='GetPoint.Get'
                self.trace(kind+' GetPoint.Get START — waiting for a point or Esc')
                waiting=perf_counter()
                try:status=getter.Get()
                except Exception as error:
                    self.trace('{} GetPoint.Get EXCEPTION after {:.3f}s: {}: {}'.format(kind,perf_counter()-waiting,type(error).__name__,error));raise
                elapsed=perf_counter()-waiting
                self.trace('{} GetPoint.Get RETURN status={} elapsed={:.3f}s'.format(kind,status,elapsed))
                if status==Rhino.Input.GetResult.Point:
                    p=getter.Point();result[0]=[p.X,p.Y,p.Z]
                    self.trace('{} accepted Point: {}'.format(kind,result[0]))
                else:
                    message='{} pick returned {} after {:.3f}s; coordinates unchanged.'.format(kind,status,elapsed)
                    self.trace(message)
                    if elapsed<.25:
                        self.error_label.Text=message+' Getter returned immediately; see Rhino F2 history.'
                    elif str(status).lower()!='cancel':self.error_label.Text=message+' See Rhino F2 history.'
            finally:
                if attached:getter.DynamicDraw-=candidate
                getter.Dispose();preview.Enabled=False;redraw()
        def pick(*args):
            # Some native modal-helper versions catch delegate exceptions.
            # Capture them INSIDE the delegate, then propagate after restoration.
            try:run_pick(*args)
            except Exception as error:
                failure[0]=error
                self.report_error(kind+' pick / '+stage[0],error)
        # Rhino suspends/restores the SAME modal Eto dialog. Toggling Visible
        # ourselves can terminate ShowModal and let the caller dispose it.
        try:Rhino.UI.EtoExtensions.PushPickButton(self.form,pick)
        finally:
            Rhino.RhinoApp.WriteLine('[AMCAD Create Port] {} PushPickButton returned after {:.3f}s; callback entered={}; point accepted={}; dialog Visible={}'.format(kind,perf_counter()-started,entered[0],result[0] is not None,getattr(self.form,'Visible','unavailable')))
        if not entered[0]:raise RuntimeError('Rhino PushPickButton returned without invoking the pick callback')
        if failure[0] is not None:raise failure[0]
        return result[0]

    def pick_position(self,sender,event):
        try:
            p=self.picked('Pick on the selected cavity surface (Esc returns to the port dialog)',surface=True)
            if p is None:return
            gap,q,n=nearest_surface(self.editor.host(self.iid),p)
            for name,value in zip(('X','Y','Z','Dx','Dy','Dz'),(q.X,q.Y,q.Z,n.X,n.Y,n.Z)):self.fields[name].Text=format(value,'.17g')
            self.message.Text='Projected to host surface; pick gap {:.3g} mm. Review position/direction.'.format(gap)
        except Exception as error:self.report_error('Pick surface position',error)

    def pick_direction(self,sender,event):
        try:
            origin=self.vector(('X','Y','Z'));p=self.picked('Pick a point along the outward port direction',origin)
            if p is not None:
                for name,value in zip(('Dx','Dy','Dz'),[p[i]-origin[i] for i in range(3)]):self.fields[name].Text=format(value,'.17g')
        except Exception as error:self.report_error('Pick direction',error)

    def submit(self,sender,event):
        self._click_count+=1;click='CLICK #{} — Create Port handler invoked'.format(self._click_count)
        Rhino.RhinoApp.WriteLine('[AMCAD Create Port] '+click)
        if self._submitting or self.created_ref is not None:
            Rhino.RhinoApp.WriteLine('[AMCAD Create Port] Duplicate click ignored; creation is running or the port is already in the draft');return
        self.progress.Text=click
        self._submitting=True;self.create_button.Enabled=False;self.error_label.Text='';stage='read fields'
        try:
            if not 0<=self.shape.SelectedIndex<3:raise ValueError('Select a section type')
            if not 0<=self.reference.SelectedIndex<len(self.references):raise ValueError('Select the original hydraulic interface')
            shape=('CIRCLE','RECTANGLE','SLOT')[self.shape.SelectedIndex];section={'type':shape}
            if shape=='CIRCLE':section['diameter_mm']=self.number('Diameter')
            else:section.update(width_mm=self.number('Width'),height_mm=self.number('Height'))
            position=self.vector(('X','Y','Z'));direction=self.vector(('Dx','Dy','Dz'));rotation=self.number('Section rotation (deg)')
            stage='make_port';self.trace(stage+' START')
            p=make_port(self.iid,self.fields['Name'].Text,position,direction,section,rotation)
            self.trace('make_port OK: name={!r} id={} position={} direction={}'.format(p['label'],p['id'],p['position_mm'],p['direction']))
            reference=self.references[self.reference.SelectedIndex];p['source_interface_id']=reference['id']
            stage='bind_port';self.trace(stage+' START: reference='+reference['id'])
            candidate=bind_port(p,reference);self.trace('bind_port OK')
            stage='validate_openings';self.trace(stage+' START')
            self.editor.validate_openings([candidate],self.trace);self.trace('validate_openings OK')
            stage='draft.add_port / refresh';self.trace(stage+' START')
            ref=self.editor.accept_physical_port(candidate)
            self.result=candidate;self.created_ref=ref
            self.trace('Draft port created and selectors/SVG refreshed: {!r}, ref={}'.format(candidate['label'],ref))
            stage='dialog.Close';self.trace('Closing dialog with successful result: '+candidate['label'])
            self.form.Close();Rhino.RhinoApp.WriteLine('[AMCAD Create Port] dialog.Close returned; result ready for parent')
        except Exception as error:
            if self.created_ref is None:self.result=None
            self.report_error(stage,error)
        finally:
            self._submitting=False
            if self.created_ref is None:self.create_button.Enabled=True


class TopologyEditor:
    """Same entry and state contract; six actions, native selectors, static SVG."""
    def __init__(self,state,request_solution):
        self.state=state;self.session=Draft(state,request_solution);self.draft=self.session.model
        self._disposed=False;self._refreshing=False;self._events=[];self._force_close=False
        self._endpoint_error=None;self._new_pending=False;self.selected_gid=None
        self.records=[];self.rows=[];self.instances=[];self.names={};self.highlight=PortHighlight()
        self.form=ef.Form();self.form.Title='AMCAD | Physical Connections — Simple SVG Overview'
        self.form.ClientSize=ed.Size(1200,850);self.form.MinimumSize=ed.Size(980,680);self.form.Resizable=True
        self.form.Owner=Rhino.UI.RhinoEtoApp.MainWindow
        self.web=ef.WebView()
        self.diagram_info=control(ef.Label,'Loading read-only connection diagram…');self.diagram_info.Wrap=ef.WrapMode.Word
        self.groups=ef.ListBox();self.groups.Height=115
        self.details=control(ef.Label,'');self.details.Wrap=ef.WrapMode.Word
        self.endpoints=[ef.DropDown() for _ in range(3)]
        self.cavities=ef.DropDown();self.inspect_port=ef.DropDown()
        self.highlight_check=control(ef.CheckBox,'Rhino highlight');self.highlight_check.Checked=True
        self.status=control(ef.Label,'Edits are drafts. Only Save writes the sidecar and updates GH.');self.status.Wrap=ef.WrapMode.Word
        self.add_pair=control(ef.Button,'Add PAIR');self.add_y3=control(ef.Button,'Add Y3')
        self.delete_button=control(ef.Button,'Delete Connection')
        controls=ef.DynamicLayout();controls.Spacing=ed.Size(6,5);controls.Padding=ed.Padding(8)
        hint=control(ef.Label,'Select New connection to add, or select a connection to edit its endpoints.');hint.Wrap=ef.WrapMode.Word
        controls.AddRow(hint)
        controls.AddRow(self.groups);controls.AddRow(self.details)
        for n,field in enumerate(self.endpoints):controls.AddRow(control(ef.Label,'Physical port '+str(n+1)+(' (Y3 only)' if n==2 else '')),field)
        controls.AddRow(self.add_pair,self.add_y3);controls.AddRow(self.delete_button)
        connections=control(ef.GroupBox,'Connections');connections.Content=controls
        ports=ef.DynamicLayout();ports.Spacing=ed.Size(6,5);ports.Padding=ed.Padding(8)
        ports.AddRow(control(ef.Label,'Cavity for new physical port'));ports.AddRow(self.cavities)
        add_port=control(ef.Button,'Add Physical Port');ports.AddRow(add_port)
        port_section=control(ef.GroupBox,'Add Physical Port');port_section.Content=ports
        inspect=ef.DynamicLayout();inspect.Spacing=ed.Size(6,5);inspect.Padding=ed.Padding(8)
        inspect.AddRow(control(ef.Label,'Inspect a physical port'));inspect.AddRow(self.inspect_port);inspect.AddRow(self.highlight_check)
        inspect_section=control(ef.GroupBox,'Inspect');inspect_section.Content=inspect
        sections=ef.DynamicLayout();sections.Spacing=ed.Size(6,10)
        for section in (connections,port_section,inspect_section):sections.AddRow(section)
        sections.AddRow(None)
        scroll=ef.Scrollable();scroll.Content=sections
        save=control(ef.Button,'Save');discard=control(ef.Button,'Discard')
        actions=ef.DynamicLayout();actions.Spacing=ed.Size(6,5);actions.AddRow(save,discard);actions.AddRow(self.status)
        left=ef.TableLayout();left.Spacing=ed.Size(5,5)
        right=ef.TableLayout();right.Spacing=ed.Size(5,10)
        for panel,widgets in ((left,((self.web,True),(self.diagram_info,False))),
                              (right,((scroll,True),(actions,False)))):
            for widget,stretch in widgets:
                row=ef.TableRow();row.Cells.Add(ef.TableCell(widget,True));row.ScaleHeight=stretch;panel.Rows.Add(row)
        split=ef.Splitter();split.Orientation=ef.SplitterOrientation.Horizontal
        split.Panel1=left;split.Panel2=right;split.Panel1MinimumSize=350;split.Panel2MinimumSize=440
        split.FixedPanel=ef.SplitterFixedPanel.Panel2;split.Position=720
        root=ef.TableLayout();root.Padding=ed.Padding(10);root.Spacing=ed.Size(5,5)
        row=ef.TableRow();row.Cells.Add(ef.TableCell(split,True));row.ScaleHeight=True;root.Rows.Add(row)
        self.form.Content=root
        for obj,name,handler in [(self.groups,'SelectedIndexChanged',self.selection_changed),(self.inspect_port,'SelectedIndexChanged',self.inspect_changed),
                                 (self.highlight_check,'CheckedChanged',self.callback(self.update_highlight)),(self.web,'DocumentLoaded',self.diagram_loaded),
                                 (self.add_pair,'Click',self.callback(lambda:self.create_group(2))),(self.add_y3,'Click',self.callback(lambda:self.create_group(3))),
                                 (self.delete_button,'Click',self.callback(self.delete)),(add_port,'Click',self.callback(self.add_port)),
                                 (save,'Click',self.callback(self.save)),(discard,'Click',self.callback(self.discard)),
                                 (self.form,'Closing',self.closing),(self.form,'Closed',self.closed)]:self.attach(obj,name,handler)
        for field in self.endpoints:self.attach(field,'SelectedIndexChanged',self.endpoint_changed)
        self.refresh()

    def attach(self,obj,name,handler):
        ev=getattr(obj,name);ev+=handler;self._events.append((obj,name,handler))

    @property
    def Visible(self):return not self._disposed and self.form.Visible
    def Show(self):self.form.Show()
    def BringToFront(self):self.form.BringToFront()
    def Close(self,force=False):self._force_close=force;self.form.Close()
    def pending(self):return self.draft.doc!=self.state['model'].doc or self._endpoint_error is not None or self._new_pending

    def callback(self,action):
        def handler(sender,event):self.guard(action)
        return handler

    def guard(self,action):
        if self._disposed:return
        try:action()
        except Exception as error:self.status.Text='ERROR: '+str(error)

    def refresh(self,gid=None):
        previous_cavity=self.instances[self.cavities.SelectedIndex][0] if 0<=self.cavities.SelectedIndex<len(self.instances) else None
        self._refreshing=True
        try:
            self.records=overview.catalog(self.draft);self.names={r['ref']:r['port_name'] for r in self.records}
            self.rows=overview.connections(self.draft);self.selected_gid=gid
            self.groups.DataStore=Array[String](['[New connection]']+[r['text'] for r in self.rows])
            self.groups.SelectedIndex=next((i+1 for i,r in enumerate(self.rows) if r['id']==gid),0)
            choices=['(select physical port)']+[r['label']+(' [disabled]' if not r['enabled'] else '') for r in self.records]
            for field in self.endpoints:field.DataStore=Array[String](choices)
            self.inspect_port.DataStore=Array[String](['(inspect a port)']+[r['label'] for r in self.records]);self.inspect_port.SelectedIndex=0
            instances={r['ref'][0]:r['instance_name'] for r in self.records};self.instances=list(instances.items())
            self.cavities.DataStore=Array[String]([name for iid,name in self.instances])
            self.cavities.SelectedIndex=next((i for i,(iid,name) in enumerate(self.instances) if iid==previous_cavity),0 if self.instances else -1)
            self.load_endpoints()
        finally:self._refreshing=False
        self.update_diagram();self.update_highlight()

    def load_endpoints(self):
        row=next((r for r in self.rows if r['id']==self.selected_gid),None)
        refs=[r['ref'] for r in self.records]
        for index,field in enumerate(self.endpoints):
            ref=row['ports'][index] if row and index<len(row['ports']) else None
            field.SelectedIndex=refs.index(ref)+1 if ref in refs else 0
            field.Enabled=not (row and row['kind']=='PAIR' and index==2)
        self.add_pair.Enabled=self.add_y3.Enabled=(row is None);self.delete_button.Enabled=row is not None
        self.details.Text=('Editing '+row['kind']+' | ID '+row['id']+' — endpoint changes update this draft, retaining the ID.') if row else 'New connection: choose two ports for PAIR or three for Y3, then press Add.'
        self._endpoint_error=None;self._new_pending=False

    def selection_changed(self,sender,event):
        if self._refreshing:return
        index=self.groups.SelectedIndex;self.selected_gid=self.rows[index-1]['id'] if 1<=index<=len(self.rows) else None
        self._refreshing=True
        try:self.inspect_port.SelectedIndex=0;self.load_endpoints()
        finally:self._refreshing=False
        self.update_diagram();self.update_highlight()

    def read_endpoints(self,count):
        indices=[f.SelectedIndex for f in self.endpoints[:count]]
        if any(i<=0 for i in indices):raise ValueError('Select exactly {} physical ports'.format(count))
        return [self.records[i-1]['ref'] for i in indices]

    def endpoint_changed(self,sender,event):
        if self._refreshing:return
        if self.selected_gid is None:
            self._new_pending=any(f.SelectedIndex>0 for f in self.endpoints)
            self.status.Text='Choose endpoints, then Add PAIR or Add Y3. GH is unchanged.';return
        try:
            row=next(r for r in self.rows if r['id']==self.selected_gid)
            self.draft.edit_group(self.selected_gid,self.read_endpoints(len(row['ports'])))
            self._endpoint_error=None
            self.rows=overview.connections(self.draft)
            self._refreshing=True
            try:
                index=self.groups.SelectedIndex
                self.groups.DataStore=Array[String](['[New connection]']+[r['text'] for r in self.rows]);self.groups.SelectedIndex=index
            finally:self._refreshing=False
            self.update_diagram();self.update_highlight();self.status.Text='Connection updated in draft; its routing ID is unchanged. Save to publish.'
        except Exception as error:
            self._endpoint_error=str(error);self.status.Text='Invalid endpoint choice: '+str(error)+'. Fix it or reselect the connection; GH is unchanged.'

    def create_group(self,count):
        if self.selected_gid is not None:raise ValueError('Select [New connection] before adding a connection')
        gid=self.draft.add_group(self.read_endpoints(count));self.refresh(gid)
        self.status.Text='Added {} in draft. Save to update GH.'.format('PAIR' if count==2 else 'Y3')

    def delete(self):
        if self.selected_gid is None:raise ValueError('Select a connection first')
        self.draft.delete_group(self.selected_gid);self.refresh();self.status.Text='Connection deleted in draft. Save to update GH.'

    def update_diagram(self):
        records=overview.catalog(self.draft)
        self.diagram_info.Text='Read-only diagram: {} cavities, {} ports, {} connections. Loading SVG…'.format(len({r['ref'][0] for r in records}),len(records),len(self.draft.doc['groups']))
        try:self.web.LoadHtml(overview.document(self.draft,self.selected_gid),None)
        except Exception as error:
            self.diagram_info.Text='Diagram load error: '+str(error)
            Rhino.RhinoApp.WriteLine(self.diagram_info.Text)

    def diagram_loaded(self,sender,event):
        if self._disposed:return
        records=overview.catalog(self.draft)
        self.diagram_info.Text='Read-only diagram loaded: {} cavities | {} physical ports | {} PAIR/Y3 connections. Edit using the controls on the right.'.format(len({r['ref'][0] for r in records}),len(records),len(self.draft.doc['groups']))

    def inspect_changed(self,sender,event):
        if not self._refreshing:self.update_highlight()

    def update_highlight(self):
        self.highlight.ports=[];self.highlight.cavity=None
        if self.highlight_check.Checked:
            index=self.inspect_port.SelectedIndex;ports=self.draft.all_ports()
            if index>0:self.highlight.ports=[ports[self.records[index-1]['ref']]]
            elif self.selected_gid:
                row=next((g for g in self.draft.doc['groups'] if g['id']==self.selected_gid),None)
                if row:self.highlight.ports=[ports[tuple(r)] for r in row['ports']]
        self.highlight.Enabled=bool(self.highlight.ports);redraw()

    def host(self,iid):
        host=self.state.get('cavities',{}).get(iid)
        if host is None:raise ValueError('Upstream Geometry & Placement cavity Brep is unavailable; recompute the existing definition first')
        return host

    def add_port(self):
        index=self.cavities.SelectedIndex
        if not 0<=index<len(self.instances):raise ValueError('Select the cavity for the new port')
        iid=self.instances[index][0];self.host(iid);dialog=PhysicalPortDialog(self,iid)
        try:
            Rhino.RhinoApp.WriteLine('[AMCAD Create Port] ShowModal START: cavity='+iid)
            dialog.form.ShowModal(self.form)
            Rhino.RhinoApp.WriteLine('[AMCAD Create Port] ShowModal returned: result={} created_ref={} extra_ports={}'.format(dialog.result is not None,dialog.created_ref,len(self.draft.doc['extra_ports'])))
            if dialog.created_ref is not None:
                if dialog.result is None or dialog.created_ref not in self.draft.all_ports():raise ValueError('Successful dialog result did not reach draft extra_ports')
                self.status.Text='Created physical port "{}" in draft. Diagram/dropdowns refreshed. Save to apply to GH.'.format(dialog.result['label'])
                Rhino.RhinoApp.WriteLine('[AMCAD Create Port] CONFIRMED: '+self.status.Text)
            else:self.status.Text='Physical port creation cancelled; no port added.'
        except Exception as error:
            self.status.Text='CREATE PORT ERROR: '+str(error)+' — see Rhino F2 history'
            Rhino.RhinoApp.WriteLine('[AMCAD Create Port] Parent/modal error: '+traceback.format_exc())
        finally:dialog.dispose()

    def accept_physical_port(self,candidate):
        """Commit an already geometry-validated candidate to draft, never GH."""
        before=deepcopy(self.draft.doc)
        try:
            ref=self.draft.add_port(candidate)
            self.refresh()
            self.status.Text='Created physical port "{}" in draft. Save to apply to GH.'.format(candidate['label'])
            Rhino.RhinoApp.WriteLine('[AMCAD Create Port] draft.extra_ports {} -> {}; SVG/dropdowns refreshed'.format(len(before['extra_ports']),len(self.draft.doc['extra_ports'])))
            return ref
        except Exception:
            self.draft.doc=before
            try:self.refresh()
            except Exception:Rhino.RhinoApp.WriteLine('[AMCAD Create Port] Refresh after rollback failed: '+traceback.format_exc())
            raise

    def save(self):
        from time import perf_counter
        if getattr(self,'_saving',False):return
        if self._endpoint_error:raise ValueError('Fix or reset the invalid endpoint selection before Save')
        if self._new_pending:raise ValueError('Add the pending PAIR/Y3 or reselect [New connection] to clear it before Save')
        started=perf_counter();self._saving=True
        def trace(message):
            text='[AMCAD Save +{:.3f}s] {}'.format(perf_counter()-started,message)
            checkpoint(message, elapsed=perf_counter()-started, stage_context='Save')
            Rhino.RhinoApp.WriteLine(text);self.status.Text=text
        try:
            trace('Physical opening validation START')
            self.validate_openings()
            trace('Physical opening validation DONE')
            self.session.publish(True,trace=trace)
            if self.state.get('recovery_mode'):
                trace('Save callback DONE; RECOVERY MODE: sidecar saved, downstream publication withheld.')
            else:trace('Save callback DONE; GH update requested. Unchanged route IDs/settings retained.')
        except Exception as error:
            trace('FAILED: '+type(error).__name__+': '+str(error))
            Rhino.RhinoApp.WriteLine(traceback.format_exc());raise
        finally:self._saving=False

    def discard(self):
        self.session.discard();self.draft=self.session.model;self.refresh()
        self.status.Text='Discarded draft. Sidecar and GH remain unchanged.'

    def validate_openings(self, additional=None, trace=None):
        ports=self.draft.all_ports()
        candidates=additional if additional is not None else [ports[key(p)] for p in self.draft.doc['extra_ports'] if list(key(p)) not in self.draft.doc['disabled']]
        for p in candidates:
            gap,point,normal=nearest_surface(self.host(p['instance_id']),p['position_mm'])
            if trace:trace('Host check: gap={:.9g} mm, limit={:.9g} mm; outward dot={:.9g}'.format(gap,max(Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance*5,.02),sum(p['direction'][i]*v for i,v in enumerate((normal.X,normal.Y,normal.Z)))))
            if gap>max(Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance*5,.02):raise ValueError('Additional port is no longer on its host surface: '+p['label'])
            if sum(p['direction'][i]*v for i,v in enumerate((normal.X,normal.Y,normal.Z)))<=1e-6:raise ValueError('Additional port direction must face outward')
            def radius(port):
                s=port['section'];return float(s['diameter_mm'])/2 if s['type']=='CIRCLE' else math.hypot(float(s['width_mm']),float(s['height_mm']))/2
            for ref,other in ports.items():
                if ref==key(p) or ref[0]!=p['instance_id'] or list(ref) in self.draft.doc['disabled']:continue
                if math.dist(p['position_mm'],other['position_mm'])<radius(p)+radius(other):
                    if trace:trace('Footprint conflict with {}: separation={:.9g} mm, required={:.9g} mm'.format(other.get('label',ref[1]),math.dist(p['position_mm'],other['position_mm']),radius(p)+radius(other)))
                    raise ValueError('Port footprints may overlap. Move or disable the conflicting opening: '+str(other.get('label',ref[1])))

    def closing(self,sender,event):
        if not self._force_close and self.pending():
            answer=ef.MessageBox.Show(self.form,'Discard unsaved topology changes and close?','AMCAD',ef.MessageBoxButtons.YesNo,ef.MessageBoxType.Question)
            if answer!=ef.DialogResult.Yes:event.Cancel=True

    def closed(self,sender,event):
        self._disposed=True;self.highlight.Enabled=False;self.highlight.ports=[];self.highlight.cavity=None;redraw()
        if self.state.get('window') is self:self.state['window']=None
        for obj,name,handler in self._events:
            ev=getattr(obj,name);ev-=handler
        self._events=[];self.web.Dispose()
