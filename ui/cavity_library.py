"""Independent cavity management and explicit instance-to-interface mapping."""
from copy import deepcopy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,
    QTableWidgetItem,QHeaderView,QComboBox,QFormLayout,QDialogButtonBox,QInputDialog,QCheckBox,QListWidget,QListWidgetItem,QMessageBox,QScrollArea,QWidget)


class PortMappingDialog(QDialog):
    def __init__(self,definition,cavity,mapping=None,parent=None):
        super().__init__(parent);self.setWindowTitle('Map Schematic Ports to Cavity Interfaces')
        self.mapping=None;self.controls={};self.cavity=cavity
        root=QVBoxLayout(self);root.addWidget(QLabel('Choose each association explicitly. Every interface must be used once.'))
        scroll=QScrollArea();scroll.setWidgetResizable(True);content=QWidget();form=QFormLayout(content);scroll.setWidget(content);root.addWidget(scroll);self.resize(560,480)
        for port in definition.ports:
            combo=QComboBox();combo.addItem('Choose an interface…',None)
            for index,m in enumerate(cavity.interfaces):combo.addItem(f'Interface {index+1} ({m.interface_type})',m.id)
            selected=(mapping or {}).get(port.id)
            if selected:combo.setCurrentIndex(combo.findData(selected))
            self.controls[port.id]=combo;form.addRow(port.display_name,combo)
        self.feedback=QLabel();root.addWidget(self.feedback)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);root.addWidget(buttons)
        buttons.accepted.connect(self.submit);buttons.rejected.connect(self.reject)

    def submit(self):
        mapping={port:combo.currentData() for port,combo in self.controls.items()}
        values=list(mapping.values())
        if None in values or len(values)!=len(set(values)) or set(values)!={m.id for m in self.cavity.interfaces}:
            self.feedback.setText('Select a complete one-to-one mapping; repeated interfaces are not allowed.');return
        self.mapping=mapping;self.accept()


class CavityLibraryDialog(QDialog):
    def __init__(self,owner,instance_id=None):
        super().__init__(owner);self.owner=owner;self.instance_id=instance_id
        self.setWindowTitle('Assign Cavity' if instance_id else 'Cavity Library');self.resize(1000,600)
        root=QVBoxLayout(self);root.addWidget(QLabel('Library: '+str(owner.cavity_library.directory)))
        if owner.cavity_library.errors:
            errors=QLabel('Could not load: '+'; '.join(owner.cavity_library.errors));errors.setWordWrap(True);root.addWidget(errors)
        if instance_id:
            i=owner.project.instances[instance_id]
            root.addWidget(QLabel(f'Assignment applies only to {i.name}'))
        self.compatible=QCheckBox('Show only valid cavities with matching hydraulic interface count')
        self.compatible.setChecked(bool(instance_id));self.compatible.setVisible(bool(instance_id));root.addWidget(self.compatible)
        self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(['Cavity name','Ports','Geometry','Revision','Usage','Status','Category'])
        self.table.setSelectionBehavior(QTableWidget.SelectRows);self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5,QHeaderView.Stretch);root.addWidget(self.table,1)
        self.usages=QListWidget();self.usages.setMaximumHeight(90);root.addWidget(QLabel('Referencing components'));root.addWidget(self.usages)
        usage_row=QHBoxLayout()
        for label,callback in [('Locate in Schematic',self.locate),('Remove Selected Reference',self.remove_reference)]:
            button=QPushButton(label);button.clicked.connect(callback);usage_row.addWidget(button)
        root.addLayout(usage_row)
        organization=QHBoxLayout()
        for label,operation in [('New Category','create'),('Rename / Move Category','rename'),('Move Entry','move')]:
            button=QPushButton(label);button.clicked.connect(lambda checked=False,op=operation:self.organize(op));organization.addWidget(button)
        root.addLayout(organization)
        self.feedback=QLabel();self.feedback.setWordWrap(True);root.addWidget(self.feedback)
        row=QHBoxLayout()
        self.buttons={}
        actions=[('New Cavity',self.new),('Open/Edit',self.edit),('Duplicate',self.duplicate),('Rename',self.rename),('Delete',self.delete)]
        for label,callback in actions:
            b=QPushButton(label);b.clicked.connect(callback);row.addWidget(b);self.buttons[label]=b
        root.addLayout(row);row=QHBoxLayout()
        for label,callback in [('Assign to Selected Component',self.assign),('Remove Assignment',self.remove_assignment),
                               ('Open Assigned Cavity',self.open_assigned),('Refresh Project Snapshot',self.refresh_snapshot),
                               ('Import Legacy for This Instance…',self.import_legacy)]:
            b=QPushButton(label);b.clicked.connect(callback);row.addWidget(b);self.buttons[label]=b
        root.addLayout(row);close=QDialogButtonBox(QDialogButtonBox.Close);close.rejected.connect(self.reject);root.addWidget(close)
        self.compatible.toggled.connect(self.refresh);self.table.itemSelectionChanged.connect(self.refresh_usage)
        current=owner.project.instances[instance_id].cavity_ref if instance_id else None
        self.refresh(current)

    def selected_id(self):
        item=self.table.item(self.table.currentRow(),0);return item.data(Qt.UserRole) if item else None

    def selected_instance(self):
        ids=self.owner.view.selected_instances()
        return self.instance_id if self.instance_id in self.owner.project.instances else ids[0] if len(ids)==1 else None

    def refresh(self,selected=None):
        if isinstance(selected,bool):selected=None
        selected=selected or self.selected_id();library=self.owner.cavity_library;project=self.owner.project
        entries=dict(project.cavities);entries.update(library.definitions)
        iid=self.selected_instance();count=len(project.definitions[project.instances[iid].definition_id].ports) if iid else None
        records=[]
        for cavity in sorted(entries.values(),key=lambda c:(c.name.casefold(),c.id)):
            try:cavity.validate();valid=True
            except ValueError as error:valid=False;reason=str(error)
            if self.compatible.isChecked() and iid and (not valid or count!=cavity.port_count):continue
            status=library.status(project,cavity.id)
            if not valid:status+=' · INVALID: '+reason
            records.append((cavity,status))
        self.table.blockSignals(True)
        self.table.setRowCount(len(records))
        for row,(cavity,status) in enumerate(records):
            for col,value in enumerate([cavity.name,cavity.port_count,cavity.geometry_type,cavity.revision,len(project.cavity_usage(cavity.id)),status,library.category_for(cavity)]):
                item=QTableWidgetItem(str(value));item.setData(Qt.UserRole,cavity.id);item.setToolTip(library.category_for(cavity));self.table.setItem(row,col,item)
                if col==0:
                    from ui.library_preview import cavity_icon
                    item.setIcon(cavity_icon(cavity))
            if cavity.id==selected:self.table.selectRow(row)
        if self.table.currentRow()<0 and records:self.table.selectRow(0)
        self.table.blockSignals(False);self.refresh_usage()
        for label in ('Assign to Selected Component','Remove Assignment','Open Assigned Cavity','Import Legacy for This Instance…'):
            self.buttons[label].setEnabled(iid is not None)
        self.buttons['Remove Assignment'].setEnabled(bool(iid and project.instances[iid].cavity_ref))
        self.buttons['Import Legacy for This Instance…'].setVisible(bool(iid and project.definitions[project.instances[iid].definition_id].physical.cavity_type!='NONE'))
        self.owner.cavity_panel.refresh()

    def cavity(self):
        cid=self.selected_id()
        return self.owner.cavity_library.definitions.get(cid) or self.owner.project.cavities.get(cid)

    def run(self,operation):
        try:return operation()
        except (ValueError,OSError,KeyError) as error:self.feedback.setText(str(error))

    def new(self):
        cavity=self.owner.new_cavity()
        if cavity:
            self.refresh(cavity.id)
            if self.instance_id:self.assign()

    def edit(self):
        cavity=self.cavity()
        if cavity:
            saved=self.owner.edit_cavity(cavity.id)
            self.refresh(saved.id if saved else cavity.id)

    def duplicate(self):
        cavity=self.cavity()
        if cavity:
            saved=self.run(lambda:self.owner.cavity_library.save(cavity.duplicate(),allow_legacy=True))
            if saved:self.refresh(saved.id)

    def rename(self):
        cavity=self.cavity()
        if not cavity:return
        names=', '.join(i.name for i in self.owner.project.cavity_usage(cavity.id))
        name,ok=QInputDialog.getText(self,'Rename Cavity','Name'+(f' (affects {names})' if names else ''),text=cavity.name)
        if ok:
            edited=deepcopy(cavity);edited.name=name.strip()
            def save_name():
                try:edited.validate()
                except ValueError:
                    # Renaming an imported draft does not repair or hide invalid geometry.
                    return self.owner.cavity_library.save(edited,allow_legacy=True)
                return self.owner.save_library_cavity(edited)
            saved=self.run(save_name)
            if saved:self.refresh(saved.id)

    def delete(self):
        cid=self.selected_id()
        if cid:self.run(lambda:self.owner.cavity_library.delete(cid,self.owner.project));self.refresh()

    def assign(self):
        iid=self.selected_instance();cavity=self.cavity()
        if not iid or cavity is None:self.feedback.setText('Select one component and a cavity');return
        def perform():
            instance=self.owner.project.instances[iid];definition=self.owner.project.effective_definition(iid)
            cavity.validate()
            if cavity.port_count!=len(definition.ports):raise ValueError('Hydraulic interface count is incompatible')
            mapping=instance.port_mapping if instance.cavity_ref==cavity.id else None
            dialog=PortMappingDialog(definition,cavity,mapping,self)
            if dialog.exec()!=QDialog.Accepted:return
            self.owner.project.assign_cavity(iid,cavity,dialog.mapping);self.owner.record_change()
            self.feedback.setText(f'Assigned {cavity.name} to {instance.name} only');self.refresh(cavity.id);self.accept()
        self.run(perform)

    def remove_assignment(self):
        iid=self.selected_instance()
        if not iid:return
        if self.instance_id is None and QMessageBox.question(self,'Remove Cavity Assignment',f'Remove the assignment from {self.owner.project.instances[iid].name}?',QMessageBox.Yes|QMessageBox.No)!=QMessageBox.Yes:return
        self.owner.remove_assignment(iid);self.refresh()

    def open_assigned(self):
        iid=self.selected_instance()
        if iid:
            cavity_id=self.owner.project.instances[iid].cavity_ref
            if cavity_id:self.owner.edit_cavity(cavity_id);self.refresh(cavity_id)
            else:self.feedback.setText('This component has no cavity assignment')

    def refresh_snapshot(self):
        cid=self.selected_id()
        if cid:
            def perform():
                cavity=self.owner.cavity_library.definitions.get(cid)
                if cavity is None:raise ValueError('Library cavity is missing; saved snapshot remains available')
                self.owner.project.update_cavity(cavity);self.owner.record_change();self.refresh(cid)
            self.run(perform)

    def import_legacy(self):
        iid=self.selected_instance()
        if iid:
            imported=self.run(lambda:self.owner.cavity_library.import_legacy(self.owner.project,iid))
            if imported:
                cavity,mapping=imported
                self.compatible.setChecked(False);self.refresh(cavity.id)
                self.feedback.setText('Imported an independent cavity for this instance. Legacy geometry remains unchanged. Edit/repair it, then assign with explicit mapping.')
                self.owner.statusBar().showMessage(self.feedback.text())

    def refresh_usage(self):
        self.usages.clear()
        for instance in self.owner.project.cavity_usage(self.selected_id()):
            item=QListWidgetItem(instance.name);item.setData(Qt.UserRole,instance.id);self.usages.addItem(item)

    def locate(self):
        item=self.usages.currentItem()
        self.owner.locate_cavity(self.selected_id(),item.data(Qt.UserRole) if item else None)

    def remove_reference(self):
        item=self.usages.currentItem()
        if item is None:self.feedback.setText('Select a referencing component');return
        if QMessageBox.question(self,'Remove Cavity Assignment',f'Remove the assignment from {item.text()}?',QMessageBox.Yes|QMessageBox.No)!=QMessageBox.Yes:return
        self.owner.remove_assignment(item.data(Qt.UserRole));self.refresh()

    def organize(self,operation):
        from ui.library_organization import category_action
        self.run(lambda:category_action(self,self.owner.cavity_library,operation,self.selected_id()))
        self.refresh();self.owner.cavity_panel.refresh()
