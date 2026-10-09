from pathlib import Path
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QDockWidget, QPushButton,
                               QFileDialog, QMessageBox, QInputDialog, QLabel, QDialog,
                               QFormLayout, QLineEdit, QComboBox, QDialogButtonBox)
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtCore import Qt
from core.project import Project
from core.history import ProjectHistory
from core.library import ComponentLibrary
from core.cavity_library import CavityLibrary
from core.graph import save_graph
from ui.component_library import ComponentLibraryPanel
from ui.schematic_view import SchematicView


class MainWindow(QMainWindow):
    def __init__(self, library_directory=None, cavity_library_directory=None):
        super().__init__()
        self.project = Project()
        self.history = ProjectHistory(self.project)
        self.library = ComponentLibrary(library_directory)
        # Explicit component-library locations isolate cavity data too (tests/portable installs).
        cavity_path=cavity_library_directory if cavity_library_directory is not None else Path(library_directory).parent/'cavities' if library_directory is not None else None
        self.cavity_library=CavityLibrary(cavity_path)
        self.path = None
        self.clipboard_data = None
        self.paste_count = 0
        self.resize(1200,800)
        self.view = SchematicView(self.project)
        self.setCentralWidget(self.view)
        self.view.changed.connect(self.record_change)
        self.view.message.connect(lambda text: self.statusBar().showMessage(text,10000))
        self.view.properties_requested.connect(self.properties)
        self.view.component_dropped.connect(self.place)
        self.view.scene().selectionChanged.connect(self.selection_info)
        dock = QDockWidget('COMPONENT LIBRARY',self)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        panel = QWidget(); layout = QVBoxLayout(panel)
        hint = QLabel('Drag onto the canvas\nor double-click to place'); layout.addWidget(hint)
        self.library_panel = ComponentLibraryPanel(); layout.addWidget(self.library_panel)
        self.library_panel.itemDoubleClicked.connect(self.place_center)
        new = QPushButton('+ New Component'); new.clicked.connect(self.new_component); layout.addWidget(new)
        dock.setWidget(panel); self.addDockWidget(Qt.RightDockWidgetArea,dock)
        dock.setMinimumWidth(220)
        self.actions = {}
        file_menu = self.menuBar().addMenu('&File')
        edit_menu = self.menuBar().addMenu('&Edit')
        component_menu = self.menuBar().addMenu('&Component')
        cavity_menu=self.menuBar().addMenu('&Cavity')
        view_menu = self.menuBar().addMenu('&View')
        toolbar = self.addToolBar('Editing'); toolbar.setMovable(False)
        for menu, key, label, shortcut, callback in [
            (file_menu,'new','New Project',QKeySequence.New,self.new_project),
            (file_menu,'open','Open Project…',QKeySequence.Open,self.open_project),
            (file_menu,'save','Save',QKeySequence.Save,self.save_project),
            (file_menu,'save_as','Save As…',QKeySequence.SaveAs,self.save_as),
            (file_menu,'export','Export Hydraulic Graph…','Ctrl+E',self.export),
            (edit_menu,'undo','Undo',QKeySequence.Undo,self.undo),
            (edit_menu,'redo','Redo',QKeySequence.Redo,self.redo),
            (edit_menu,'copy','Copy',QKeySequence.Copy,self.copy),
            (edit_menu,'paste','Paste',QKeySequence.Paste,self.paste),
            (edit_menu,'delete','Delete Selection',QKeySequence.Delete,self.delete_selection),
            (edit_menu,'delete_line','Delete Line',None,self.delete_lines),
            (edit_menu,'select_all','Select All',QKeySequence.SelectAll,self.select_all),
            (component_menu,'create','New Component…','Ctrl+Shift+N',self.new_component),
            (component_menu,'cavity','Assign Cavity…','Ctrl+Shift+C',self.assign_cavity),
            (component_menu,'rename','Properties / Rename…','F2',self.selected_properties),
            (component_menu,'rotate','Rotate 90°','Ctrl+R',self.rotate_selection),
            (component_menu,'junction','Add 3-Way Junction','Ctrl+J',self.add_junction),
            (component_menu,'junction4','Add 4-Way Junction','Ctrl+Shift+J',lambda:self.add_junction(4)),
            (cavity_menu,'cavity_library','Cavity Library…',None,self.open_cavity_library),
            (cavity_menu,'new_cavity','New Cavity…',None,self.new_cavity),
            (view_menu,'fit','Fit Schematic','F',self.view.fit_content),
            (view_menu,'zoom_in','Zoom In','Ctrl++',lambda:self.view.zoom(1.15)),
            (view_menu,'zoom_out','Zoom Out','Ctrl+-',lambda:self.view.zoom(1/1.15)),
        ]:
            action = QAction(label,self)
            if shortcut is not None: action.setShortcut(shortcut)
            action.triggered.connect(callback); menu.addAction(action); self.actions[key]=action
            if key in {'save','undo','redo','delete','rotate','junction','fit','cavity_library'}: toolbar.addAction(action)
        self.refresh_library()
        self.update_title()
        self.statusBar().showMessage('Drag components • click a free port to draw a line • middle-drag to pan • wheel to zoom')
        errors=self.library.errors+self.cavity_library.errors
        if errors:
            self.statusBar().showMessage('Some library files could not be loaded: '+'; '.join(errors))

    def refresh_library(self):
        self.available_definitions = dict(self.library.definitions)
        self.available_definitions.update(self.project.definitions)
        self.library_panel.populate(self.available_definitions)

    def selection_info(self):
        names = [self.project.instances[i].name for i in self.view.selected_instances()]
        if names:
            self.statusBar().showMessage('Selected: '+', '.join(names)+' · F2 properties · Ctrl+R rotate')
        elif self.view.selected_connections():
            self.statusBar().showMessage('Line selected · drag segment handles or bend points · Delete removes the line')

    def update_title(self):
        dirty = self.history.is_dirty(self.project)
        name = self.path.name if self.path else self.project.metadata['name']
        self.setWindowTitle(f'{"*" if dirty else ""}{name} — AMCAD Hydraulic Schematic')
        if self.actions:
            self.actions['undo'].setEnabled(self.history.index>0)
            self.actions['redo'].setEnabled(self.history.index<len(self.history.states)-1)

    def record_change(self):
        self.history.record(self.project)
        self.update_title()

    def error(self, error):
        QMessageBox.warning(self,'AMCAD',str(error))

    def place(self, definition_id, x, y):
        try:
            instance = self.project.add_instance(self.available_definitions[definition_id],x,y)
            self.view.rebuild([instance.id]); self.record_change(); self.refresh_library()
        except (ValueError,KeyError) as error: self.error(error)

    def place_center(self,item):
        pos = self.view.mapToScene(self.view.viewport().rect().center())
        self.place(item.data(Qt.UserRole),pos.x(),pos.y())

    def add_junction(self, ways=3):
        # QAction passes its checked flag; retain the default three-way shortcut.
        if isinstance(ways, bool): ways = 3
        pos = self.view.mapToScene(self.view.viewport().rect().center())
        self.place(f'junction-{ways}',pos.x(),pos.y())
        self.statusBar().showMessage('Connect each branch to a free junction port. Crossing lines are not connected.')

    def delete_selection(self):
        instance_ids = self.view.selected_instances()
        connection_ids = self.view.selected_connections()
        for connection_id in connection_ids: self.project.connections.pop(connection_id,None)
        for instance_id in instance_ids: self.project.remove_instance(instance_id)
        self.view.rebuild(); self.record_change()

    def delete_lines(self):
        for connection_id in self.view.selected_connections():
            self.project.connections.pop(connection_id, None)
        self.view.rebuild(); self.record_change()

    def rotate_selection(self):
        ids = self.view.selected_instances()
        for instance_id in ids:
            self.project.rotate(instance_id)
        self.view.rebuild(ids); self.record_change()

    def select_all(self):
        for item in self.view.component_items.values(): item.setSelected(True)
        for item in self.view.wires.values(): item.setSelected(True)

    def copy(self):
        ids = self.view.selected_instances()
        if ids:
            self.clipboard_data = self.project.copy_subgraph(ids)
            self.paste_count=0
            self.statusBar().showMessage(f'Copied {len(ids)} component(s) and lines between them')

    def paste(self):
        if self.clipboard_data:
            self.paste_count += 1
            ids = self.project.paste_subgraph(self.clipboard_data,30*self.paste_count)
            self.view.rebuild(ids); self.record_change(); self.refresh_library()

    def undo(self):
        self.project = self.history.undo(); self.sync_project()

    def redo(self):
        self.project = self.history.redo(); self.sync_project()

    def sync_project(self):
        self.view.project=self.project; self.view.rebuild(); self.refresh_library(); self.update_title()

    def selected_properties(self):
        ids = self.view.selected_instances()
        if len(ids)==1: self.properties(ids[0])
        else: self.statusBar().showMessage('Select one component to edit its properties')

    def properties(self, instance_id):
        instance = self.project.instances[instance_id]
        dialog = QDialog(self); dialog.setWindowTitle('Component Properties')
        form = QFormLayout(dialog)
        name = QLineEdit(instance.name)
        rotation = QComboBox(); rotation.addItems(['0','90','180','270']); rotation.setCurrentText(str(instance.rotation))
        form.addRow('Definition',QLabel(self.project.definitions[instance.definition_id].name))
        form.addRow('Persistent ID',QLabel(instance.id))
        form.addRow('Name',name); form.addRow('Rotation (degrees)',rotation)
        cavity=QPushButton('Assign Cavity…')
        cavity.clicked.connect(lambda:self.assign_cavity(instance_id))
        assigned=self.project.cavities.get(instance.cavity_ref)
        form.addRow('Cavity',QLabel(assigned.name+' · '+self.cavity_library.status(self.project,assigned.id) if assigned else 'Unassigned'+(' · legacy embedded data available for import' if self.project.definitions[instance.definition_id].physical.cavity_type!='NONE' else '')))
        form.addRow(cavity)
        for node in self.project.nodes.values():
            if node.instance_id==instance_id:
                form.addRow(node.port_id,QLabel(node.id))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        form.addRow(buttons)
        buttons.rejected.connect(dialog.reject)
        def apply():
            try: self.project.rename(instance_id,name.text())
            except ValueError as error: self.error(error); return
            instance.rotation=int(rotation.currentText()); dialog.accept()
            self.view.rebuild([instance_id]); self.record_change()
        buttons.accepted.connect(apply)
        dialog.exec()

    def open_cavity_library(self):
        from ui.cavity_library import CavityLibraryDialog
        CavityLibraryDialog(self).exec()

    def assign_cavity(self,instance_id=None):
        from ui.cavity_library import CavityLibraryDialog
        if instance_id is None or isinstance(instance_id,bool):
            ids=self.view.selected_instances()
            if len(ids)!=1:self.statusBar().showMessage('Select one component instance to assign a cavity');return
            instance_id=ids[0]
        CavityLibraryDialog(self,instance_id).exec()

    def new_cavity(self):
        from ui.cavity_editor import CavityEditor
        dialog=CavityEditor(parent=self,cavity_library=self.cavity_library,save_callback=self.save_library_cavity)
        if dialog.exec()==QDialog.Accepted:
            self.statusBar().showMessage('Saved independent cavity '+dialog.result_cavity.name)
            return dialog.result_cavity

    def edit_cavity(self,cavity_id):
        from ui.cavity_editor import CavityEditor
        cavity=self.cavity_library.definitions.get(cavity_id) or self.project.cavities.get(cavity_id)
        if cavity is None:self.statusBar().showMessage('Cavity reference is missing');return
        dialog=CavityEditor(parent=self,cavity_definition=cavity,cavity_library=self.cavity_library,save_callback=self.save_library_cavity)
        usages=self.project.cavity_usage(cavity_id)
        warning=self.cavity_library.status(self.project,cavity_id)
        if len(usages)>1:warning+=' · Shared cavity: saving updates '+', '.join(i.name for i in usages)+'. Use Save As New for an independent copy.'
        message=QLabel(warning);message.setWordWrap(True);dialog.layout().insertWidget(0,message)
        if dialog.exec()==QDialog.Accepted:return dialog.result_cavity

    def save_library_cavity(self,cavity):
        from copy import deepcopy
        if cavity.id in self.project.cavities and cavity.id not in self.cavity_library.definitions:
            raise ValueError('Library reference is missing. Use Save As New to preserve this snapshot as an independent library cavity.')
        # Confirm that interface changes cannot invalidate any active mapping before writing.
        candidate=deepcopy(self.project);candidate.update_cavity(cavity)
        saved=self.cavity_library.save(cavity)
        self.project.update_cavity(saved);self.record_change()
        self.statusBar().showMessage(f'Saved cavity {saved.name} · revision {saved.revision}')
        return saved

    def new_component(self):
        from ui.node_wizard import NodeWizard
        dialog = NodeWizard(self)
        if dialog.exec()==QDialog.Accepted:
            try:
                self.library.save(dialog.definition)
                self.refresh_library()
                self.statusBar().showMessage(f'Saved {dialog.definition.name} in the component library')
            except (ValueError,OSError) as error: self.error(error)

    def confirm_discard(self):
        if not self.history.is_dirty(self.project): return True
        answer = QMessageBox.question(self,'Unsaved project','Save changes before continuing?',
                                      QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if answer==QMessageBox.Cancel: return False
        if answer==QMessageBox.Save: return self.save_project()
        return True

    def new_project(self):
        if not self.confirm_discard(): return
        self.project=Project(); self.path=None; self.history=ProjectHistory(self.project)
        self.sync_project(); self.view.fit_content()

    def load_path(self,path):
        project = Project.load(path)
        self.project=project; self.path=Path(path); self.history=ProjectHistory(project)
        self.sync_project(); self.view.fit_content()

    def open_project(self):
        if not self.confirm_discard(): return
        path,_ = QFileDialog.getOpenFileName(self,'Open AMCAD Project','','AMCAD Project (*.json)')
        if path:
            try: self.load_path(path)
            except (OSError,ValueError,KeyError,TypeError,StopIteration) as error: self.error(error)

    def save_to(self,path):
        self.project.save(path)
        self.path=Path(path); self.history.mark_saved(self.project); self.update_title()
        self.statusBar().showMessage(f'Saved {self.path.name}')

    def save_project(self):
        if self.path is None: return self.save_as()
        try: self.save_to(self.path); return True
        except (OSError,ValueError) as error: self.error(error); return False

    def save_as(self):
        path,_=QFileDialog.getSaveFileName(self,'Save AMCAD Project',str(self.path or 'project.amcad.json'),'JSON (*.json)')
        if not path: return False
        if not path.lower().endswith('.json'): path += '.json'
        try: self.save_to(path); return True
        except (OSError,ValueError) as error: self.error(error); return False

    def export_to(self,path):
        save_graph(self.project,path)

    def export(self):
        path,_=QFileDialog.getSaveFileName(self,'Export Hydraulic Graph','hydraulic.graph.json','JSON (*.json)')
        if path:
            if not path.lower().endswith('.json'): path += '.json'
            try:
                self.export_to(path); self.statusBar().showMessage('Hydraulic graph exported')
            except (OSError,ValueError) as error: self.error(error)

    def closeEvent(self,event):
        if self.confirm_discard(): event.accept()
        else: event.ignore()
