"""Independent cavity management and explicit instance-to-interface mapping."""
from copy import deepcopy
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QComboBox,QFormLayout,QDialogButtonBox,QInputDialog,QCheckBox,QListWidget,QListWidgetItem,QMessageBox,QScrollArea,QWidget,QMenu,QLineEdit,QToolButton,QTreeWidgetItem)


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


class CavityBrowser(QWidget):
    assigned=Signal()
    def __init__(self,owner,instance_id=None):
        super().__init__();self.owner=owner;self.instance_id=instance_id
        from ui.library_browser import LibraryTree
        root=QVBoxLayout(self);self.search=QLineEdit();self.search.setPlaceholderText('Search cavities…');self.search.setToolTip('Library: '+str(owner.cavity_library.directory));root.addWidget(self.search)
        if instance_id:root.addWidget(QLabel('Assignment applies only to '+owner.project.instances[instance_id].name))
        self.compatible=QCheckBox('Matching valid cavities only');self.compatible.setChecked(bool(instance_id));self.compatible.setVisible(bool(instance_id));root.addWidget(self.compatible)
        self.tree=LibraryTree();self.tree.library_kind="cavity";root.addWidget(self.tree,1)
        self.tree.entry_move_requested.connect(lambda identifier,path:self.run_and_refresh(lambda:owner.cavity_library.move_entry(identifier,path)))
        self.details=QWidget();details=QVBoxLayout(self.details);details.setContentsMargins(0,0,0,0)
        self.status=QLabel();self.status.setWordWrap(True);details.addWidget(self.status)
        self.usages=QListWidget();self.usages.setMaximumHeight(85);details.addWidget(self.usages)
        row=QHBoxLayout();self.locate_button=QToolButton();self.locate_button.setText('Locate in Schematic');self.locate_button.clicked.connect(self.locate);row.addWidget(self.locate_button)
        self.remove_button=QToolButton();self.remove_button.setText('Remove Selected Reference');self.remove_button.clicked.connect(self.remove_reference);row.addWidget(self.remove_button);details.addLayout(row);root.addWidget(self.details)
        self.feedback=QLabel('Could not load: '+'; '.join(owner.cavity_library.errors) if owner.cavity_library.errors else '');self.feedback.setWordWrap(True);root.addWidget(self.feedback)
        create=QPushButton('+ New Cavity');create.clicked.connect(self.new);root.addWidget(create)
        self.usages.currentItemChanged.connect(lambda current,previous:self.remove_button.setEnabled(current is not None))
        self.tree.itemSelectionChanged.connect(self.refresh_usage);self.tree.customContextMenuRequested.connect(self.context_menu)
        self.tree.itemDoubleClicked.connect(lambda item,col:self.edit() if item.data(0,Qt.UserRole) else None)
        self.search.textChanged.connect(self.tree.filter);self.compatible.toggled.connect(self.refresh)
        current=owner.project.instances[instance_id].cavity_ref if instance_id else None
        self.refresh(current)

    def selected_id(self):return self.tree.selected_id()

    def selected_instance(self):
        ids=self.owner.view.selected_instances()
        return self.instance_id if self.instance_id in self.owner.project.instances else ids[0] if len(ids)==1 else None

    def refresh(self,selected=None):
        from ui.library_browser import category_paths
        from ui.library_preview import cavity_icon
        if isinstance(selected,bool):selected=None
        library=self.owner.cavity_library;project=self.owner.project
        entries=dict(project.cavities);entries.update(library.definitions)
        iid=self.selected_instance();count=len(project.effective_definition(iid).ports) if iid else None
        self.tree.begin_refresh(category_paths(library))
        used_root=QTreeWidgetItem(['In Use']);used_root.setData(0,Qt.UserRole+3,'usage');self.tree.insertTopLevelItem(0,used_root);used_root.setExpanded(True);self.tree.paths[('in-use',)]=used_root
        for cavity in sorted(entries.values(),key=lambda c:(c.name.casefold(),c.id)):
            try:cavity.validate();valid=True
            except ValueError as error:valid=False;reason=str(error)
            if self.compatible.isChecked() and iid and (not valid or count!=cavity.port_count):continue
            status=library.status(project,cavity.id)
            if not valid:status+=' · INVALID: '+reason
            usage=project.cavity_usage(cavity.id)
            text=f'{cavity.name}\n{cavity.port_count} ports · rev {cavity.revision} · {len(usage)} uses'
            item=self.tree.add_entry(library.category_for(cavity),cavity.id,text,cavity_icon(cavity),status)
            item.setData(0,Qt.UserRole+2,status)
            if usage:
                used=self.tree.add_entry(used_root,cavity.id,text+'\n'+', '.join(i.name for i in usage),cavity_icon(cavity),status)
                used.setData(0,Qt.UserRole+2,status)
        self.tree.end_refresh(selected)
        if not self.tree.currentItem() and self.tree.entries:self.tree.setCurrentItem(self.tree.entries[0])
        self.refresh_usage()
        dock=getattr(self.owner,'cavity_panel',None)
        if dock is not None and dock is not self:dock.refresh()

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
            if saved:
                if self.owner.cavity_library.category_for(cavity)!='Uncategorized':self.owner.cavity_library.move_entry(saved.id,self.owner.cavity_library.category_for(cavity))
                self.refresh(saved.id)

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
            self.feedback.setText(f'Assigned {cavity.name} to {instance.name} only');self.refresh(cavity.id);self.assigned.emit()
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
        cavity_id=self.selected_id();item=self.tree.currentItem();usages=self.owner.project.cavity_usage(cavity_id) if cavity_id else []
        self.details.setVisible(bool(cavity_id));self.status.setText(item.data(0,Qt.UserRole+2) or '' if cavity_id else '')
        self.usages.setVisible(bool(usages));self.locate_button.setEnabled(bool(usages));self.locate_button.setVisible(bool(usages));self.remove_button.setVisible(bool(usages));self.remove_button.setEnabled(False)
        for instance in usages:
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
        result=self.run(lambda:category_action(self,self.owner.cavity_library,operation,self.selected_id()))
        self.refresh();self.owner.cavity_panel.refresh()
        if isinstance(result,str):self.tree.reveal_category(result)

    def menu(self,item=None):
        from ui.library_organization import add_category_menu,category_action
        menu=QMenu(self);library=self.owner.cavity_library
        path=item.data(0,Qt.UserRole+1) if item else None
        if item and item.data(0,Qt.UserRole+3)=='usage':return menu
        if path:
            add_category_menu(menu,self,library,path,lambda callback:self.run_and_refresh(callback))
            return menu
        cavity=self.cavity() if item and item.data(0,Qt.UserRole) else None
        iid=self.selected_instance();instance=self.owner.project.instances.get(iid)
        def add(label,callback,enabled=True):
            action=menu.addAction(label);action.setEnabled(enabled);action.triggered.connect(lambda checked=False:self.run(callback));return action
        if cavity:
            available=cavity.id in library.definitions;usage=self.owner.project.cavity_usage(cavity.id)
            try:cavity.validate();valid=True
            except ValueError:valid=False
            add('Open/Edit',self.edit);add('Rename',self.rename,available);add('Duplicate',self.duplicate)
            add('Assign to Selected Component',self.assign,bool(instance and valid and len(self.owner.project.effective_definition(iid).ports)==cavity.port_count))
            add('Locate in Schematic',self.locate,bool(usage))
            add('Remove Selected Reference',self.remove_reference,self.usages.currentItem() is not None)
            add('Remove Assignment',self.remove_assignment,bool(instance and instance.cavity_ref==cavity.id))
            add('Move to Category',lambda:self.organize('move'),available)
            add('Delete',self.delete,available and not usage)
            if cavity.id in self.owner.project.cavities:add('Refresh Project Snapshot',self.refresh_snapshot,available)
        else:add('New Category',lambda:self.organize('create'))
        if instance:
            if instance.cavity_ref:add('Open Assigned Cavity',self.open_assigned)
            if self.owner.project.definitions[instance.definition_id].physical.cavity_type!='NONE':add('Import Legacy for This Instance…',self.import_legacy)
        return menu

    def run_and_refresh(self,callback):
        result=self.run(callback);self.refresh()
        if isinstance(result,str):self.tree.reveal_category(result)

    def context_menu(self,position):
        item=self.tree.itemAt(position)
        if item:self.tree.setCurrentItem(item)
        else:self.tree.setCurrentItem(None)
        self.menu(item).exec(self.tree.viewport().mapToGlobal(position))


class CavityLibraryDialog(QDialog):
    def __init__(self,owner,instance_id=None):
        super().__init__(owner);self.setWindowTitle('Assign Cavity' if instance_id else 'Cavity Library');self.resize(760,660)
        root=QVBoxLayout(self);self.browser=CavityBrowser(owner,instance_id);root.addWidget(self.browser)
        self.browser.assigned.connect(self.accept)
        close=QDialogButtonBox(QDialogButtonBox.Close);close.rejected.connect(self.reject);root.addWidget(close)

    def __getattr__(self,name):
        browser=self.__dict__.get('browser')
        if browser is not None and hasattr(browser,name):return getattr(browser,name)
        raise AttributeError(name)
