from copy import deepcopy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QPushButton,QLabel,QInputDialog,QDialogButtonBox,QMenu,QLineEdit
from ui.component_library import ComponentLibraryPanel
from ui.library_organization import category_action,add_category_menu


class ComponentLibraryActions:
    def __init__(self,owner,panel,refresh,parent,feedback=None):
        self.owner=owner;self.panel=panel;self.refresh=refresh;self.parent=parent;self.feedback=feedback
        panel.entry_move_requested.connect(lambda identifier,path:self.run(lambda:owner.library.move_entry(identifier,path)))

    def run(self,callback):
        try:
            result=callback();self.refresh()
            if isinstance(result,str):self.panel.reveal_category(result)
            return result
        except (ValueError,OSError,KeyError) as error:
            if self.feedback:self.feedback.setText(str(error))
            else:self.owner.error(error)

    def selected(self):
        identifier=self.panel.selected_id()
        if not self.owner.library.is_custom(identifier):raise ValueError('Choose a custom definition; built-ins are templates')
        return deepcopy(self.owner.library.definitions[identifier])

    def edit(self):
        from ui.node_wizard import NodeWizard
        definition=self.selected();dialog=NodeWizard(self.parent,definition,library=self.owner.library)
        if dialog.exec()==QDialog.Accepted:
            target=dialog.category.text();dialog.definition.category=definition.category
            self.owner.library.update(dialog.definition)
            if self.owner.library.category_for(dialog.definition)!=target:self.owner.library.move_entry(dialog.definition.id,target)

    def rename(self):
        definition=self.selected();name,ok=QInputDialog.getText(self.parent,'Rename Component','Name',text=definition.name)
        if ok:definition.name=name.strip();self.owner.library.update(definition)

    def duplicate(self):
        from core.port import new_id
        identifier=self.panel.selected_id();definition=deepcopy(self.owner.library.definitions.get(identifier) or self.owner.available_definitions[identifier])
        definition.id=new_id();definition.name+=' Copy';definition.revision=1
        self.owner.library.save(definition)
        self.owner.library.move_entry(definition.id,self.owner.library.category_for(self.owner.library.definitions.get(identifier,definition)))

    def delete(self):self.selected();self.owner.library.delete(self.panel.selected_id(),self.owner.project)

    def menu(self,item=None):
        menu=QMenu(self.parent);library=self.owner.library
        path=item.data(0,Qt.UserRole+1) if item else None
        if path:
            add_category_menu(menu,self.parent,library,path,self.run);return menu
        identifier=item.data(0,Qt.UserRole) if item else None
        custom=library.is_custom(identifier);used=any(i.definition_id==identifier for i in self.owner.project.instances.values())
        def add(text,callback,enabled=True):
            action=menu.addAction(text);action.setEnabled(enabled);action.triggered.connect(lambda checked=False:self.run(callback));return action
        if identifier:
            add('Place in Schematic',lambda:self.owner.place_center(item))
            add('Edit',self.edit,custom);add('Rename',self.rename,custom);add('Duplicate',self.duplicate)
            add('Move to Category',lambda:category_action(self.parent,library,'move',identifier),identifier in library.definitions)
            add('Delete',self.delete,custom and not used)
        add('Save Selected Instance to Library',self.owner.save_selected_component,len(self.owner.view.selected_instances())==1)
        if not identifier:add('New Category',lambda:category_action(self.parent,library,'create'))
        return menu

    def context_menu(self,position):
        item=self.panel.itemAt(position)
        if item:self.panel.setCurrentItem(item)
        self.menu(item).exec(self.panel.viewport().mapToGlobal(position))


class ComponentLibraryDialog(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.setWindowTitle('Component Library');self.resize(720,600)
        root=QVBoxLayout(self);self.search=QLineEdit();self.search.setPlaceholderText('Search components…');root.addWidget(self.search)
        self.panel=ComponentLibraryPanel();root.addWidget(self.panel,1);self.feedback=QLabel();root.addWidget(self.feedback)
        create=QPushButton('+ New Component');create.clicked.connect(lambda:self.actions.run(owner.new_component));root.addWidget(create)
        buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(self.reject);root.addWidget(buttons)
        self.actions=ComponentLibraryActions(owner,self.panel,self.refresh,self,self.feedback)
        self.panel.customContextMenuRequested.connect(self.actions.context_menu);self.search.textChanged.connect(self.panel.filter)
        self.panel.itemDoubleClicked.connect(lambda item,col:self.owner.place_center(item) if item.data(0,Qt.UserRole) else None);self.refresh()

    def refresh(self):self.panel.populate(self.owner.library.definitions,self.owner.library);self.owner.refresh_library()
    def selected_id(self):return self.panel.selected_id()
