"""Compact native Rhino/Eto editor; all authoritative state lives in the controller."""
import Eto.Forms as forms
import Eto.Drawing as drawing
import Rhino
from System import Array,String
import Rhino.Geometry as rg
import Rhino.Display as rd
from System.Drawing import Color


class CavitySelectionConduit(rd.DisplayConduit):
    """Draw-only overlay; never selects, bakes or modifies Rhino objects."""
    def __init__(self):
        super().__init__()
        self.geometry = None
        self.label = ''
        self.color = Color.FromArgb(255, 165, 0)

    def DrawForeground(self, e):
        brep = self.geometry
        if brep is None:
            return
        try:
            for edge in brep.Edges:
                e.Display.DrawCurve(edge, self.color, 4)
            bbox = brep.GetBoundingBox(True)
            if bbox.IsValid:
                e.Display.DrawDot(bbox.Center, self.label, self.color, Color.Black)
        except Exception:
            pass


class PlacementEditor(forms.Form):
    def __init__(self,model,on_changed,on_closed,highlight_lookup=None):
        super().__init__();self.model=model;self.on_changed=on_changed;self.on_closed=on_closed
        self.Title='AMCAD · Cavity Placement';self.ClientSize=drawing.Size(560,740);self.MinimumSize=drawing.Size(460,680);self.Padding=drawing.Padding(12)
        self._loading=False;self._records=[];self._token=None;self._baseline=[];self._display_dirty=None
        self._highlight_lookup=highlight_lookup;self._highlight=CavitySelectionConduit()
        self.search=forms.TextBox();self.search.PlaceholderText='Search schematic instance names…'
        self.instances=forms.ListBox();self.instances.Height=190
        self.heading=forms.Label();self.heading.Wrap=forms.WrapMode.Word
        self.feedback=forms.Label();self.feedback.Wrap=forms.WrapMode.Word
        self.fields=[forms.TextBox() for _ in range(6)]
        self.apply_button=forms.Button();self.apply_button.Text='Apply / Update Selected'
        self.save_button=forms.Button();self.save_button.Text='Save All Placements';self.reload_button=forms.Button();self.reload_button.Text='Reload Saved Placements'
        self.search.TextChanged+=self.search_changed;self.instances.SelectedIndexChanged+=self.selection_changed
        for field in self.fields:field.TextChanged+=self.field_changed
        self.apply_button.Click+=self.apply;self.save_button.Click+=self.save;self.reload_button.Click+=self.reload
        self.Closed+=self._closed
        layout=forms.DynamicLayout();layout.Spacing=drawing.Size(8,8)
        layout.AddRow(self.search);layout.AddRow(self.instances);layout.AddRow(self.heading)
        for label,field in zip(('X (mm)','Y (mm)','Z (mm)','Rx (°)','Ry (°)','Rz (°)'),self.fields):
            caption=forms.Label();caption.Text=label;layout.AddRow(caption,field)
        layout.AddRow(self.apply_button);layout.AddRow(self.save_button,self.reload_button);layout.AddRow(self.feedback)
        self.Content=layout
        if self.model.selected_id is None and self.model.catalog():self.model.select(self.model.catalog()[0]['id'])
        self.refresh_instances();self.load_fields();self.update_highlight()

    def refresh_instances(self):
        self._loading=True
        try:
            self._records=self.model.catalog(self.search.Text or '')
            self.instances.DataStore=Array[String]([record['name'] for record in self._records])
            self.instances.SelectedIndex=next((i for i,r in enumerate(self._records) if r['id']==self.model.selected_id),-1)
        finally:self._loading=False
        if self._token!=self.model.selection_token:self.load_fields()
        else:self.update_labels()

    def search_changed(self,sender,event):self.refresh_instances()

    def selection_changed(self,sender,event):
        if self._loading:return
        index=self.instances.SelectedIndex
        self.model.select(self._records[index]['id'] if index>=0 else None)
        self.load_fields();self.update_highlight()

    def load_fields(self):
        selected=self.model.selected_id;visible=any(r['id']==selected for r in self._records)
        self._loading=True
        try:
            self._token=self.model.selection_token
            current=self.model.placement(selected) if selected is not None else None
            values=current['translation_mm']+current['rotation_deg'] if current else [0]*6
            self._baseline=[format(value,'.17g') for value in values]
            for field,value in zip(self.fields,self._baseline):field.Text=value;field.Enabled=visible
            self.apply_button.Enabled=visible
            self.save_button.Enabled=bool(self.model.placement_path);self.reload_button.Enabled=bool(self.model.placement_path)
            self._display_dirty=self.model.dirty
            record=next((r for r in self.model.catalog() if r['id']==selected),None)
            self.heading.Text=(record['name']+'\n'+record['id']) if record else 'Select a cavity instance.'
            self.feedback.Text='Applied state has unsaved changes.' if self.model.dirty else 'Applied state matches the saved placement file.'
            if selected and not visible:self.feedback.Text='Selected instance is hidden by the search. Clear the filter to edit it.'
        finally:self._loading=False

    def pending(self):return [f.Text for f in self.fields]!=self._baseline

    def field_changed(self,sender,event):
        if not self._loading:self.feedback.Text='Unapplied edits. Click Apply / Update; switching instances discards these edits.'

    def apply(self,sender,event):
        try:
            values=[float(f.Text) for f in self.fields]
            self.model.apply_selected(values[:3],values[3:],self._token)
            self.load_fields();self.update_highlight();self.on_changed()
        except Exception as error:self.feedback.Text=str(error)

    def save(self,sender,event):
        if self.pending():self.feedback.Text='Apply or discard the pending field edits before saving.';return
        try:self.model.save();self.load_fields();self.feedback.Text='Saved the complete placement state.';self.on_changed()
        except Exception as error:self.feedback.Text=str(error)

    def reload(self,sender,event):
        if self.pending() or self.model.dirty:
            answer=forms.MessageBox.Show(self,'Reload saved placements and discard unapplied/unsaved edits?','AMCAD',forms.MessageBoxButtons.YesNo,forms.MessageBoxType.Question)
            if answer!=forms.DialogResult.Yes:return
        try:self.model.reload();self.refresh_instances();self.feedback.Text='Reloaded saved placements.';self.on_changed()
        except Exception as error:self.feedback.Text=str(error)

    def sync(self):
        # A normal GH recompute must not erase a draft. A selection/reload/external
        # selected-pose update changes the token and explicitly reloads the fields.
        self._loading=True
        try:
            records=self.model.catalog(self.search.Text or '')
            if records!=self._records:
                self._records=records;self.instances.DataStore=Array[String]([r['name'] for r in records])
                self.instances.SelectedIndex=next((i for i,r in enumerate(records) if r['id']==self.model.selected_id),-1)
        finally:self._loading=False
        if self._token!=self.model.selection_token:self.load_fields()
        else:self.update_labels()

    def update_labels(self):
        selected=self.model.selected_id;visible=any(r['id']==selected for r in self._records)
        record=next((r for r in self.model.catalog() if r['id']==selected),None)
        self.heading.Text=(record['name']+'\n'+record['id']) if record else 'Select a cavity instance.'
        self.apply_button.Enabled=visible
        for field in self.fields:field.Enabled=visible
        if selected and not visible:self.feedback.Text='Selected instance is hidden by the search. Clear the filter to edit it.'
        elif self.pending():self.feedback.Text='Unapplied edits. Click Apply / Update; switching instances discards these edits.'
        elif self._display_dirty!=self.model.dirty:self.feedback.Text='Applied state has unsaved changes.' if self.model.dirty else 'Applied state matches the saved placement file.'
        self._display_dirty=self.model.dirty
        self.update_highlight()

    def update_highlight(self):
        geometry=None;label=''
        if self._highlight_lookup is not None and self.model.selected_id is not None:
            try:
                item=self._highlight_lookup(self.model.selected_id)
                if item is not None:
                    geometry,label=item
                    if not isinstance(geometry,rg.Brep):
                        value=getattr(geometry,'Value',None)
                        geometry=value if isinstance(value,rg.Brep) else None
            except Exception:
                geometry=None
        self._highlight.geometry=geometry
        self._highlight.label=str(label)
        self._highlight.Enabled=(geometry is not None)
        doc=Rhino.RhinoDoc.ActiveDoc
        if doc is not None:doc.Views.Redraw()

    def _closed(self,sender,event):
        self._highlight.Enabled=False
        self._highlight.geometry=None
        doc=Rhino.RhinoDoc.ActiveDoc
        if doc is not None:doc.Views.Redraw()
        self.on_closed(self)


def show_editor(window):
    window.Owner=Rhino.UI.RhinoEtoApp.MainWindow
    window.Show();window.BringToFront()
