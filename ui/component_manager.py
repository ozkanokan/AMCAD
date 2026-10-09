from copy import deepcopy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QInputDialog,QDialogButtonBox
from ui.component_library import ComponentLibraryPanel
from ui.library_organization import category_action


class ComponentLibraryDialog(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.setWindowTitle('Component Library');self.resize(720,600)
        root=QVBoxLayout(self);self.panel=ComponentLibraryPanel();root.addWidget(self.panel,1);self.feedback=QLabel();root.addWidget(self.feedback)
        row=QHBoxLayout()
        for label,callback in [('New',owner.new_component),('Save Selected Instance',owner.save_selected_component),('Edit',self.edit),('Rename',self.rename),('Delete',self.delete)]:
            button=QPushButton(label);button.clicked.connect(lambda checked=False,cb=callback:self.run(cb));row.addWidget(button)
        root.addLayout(row);row=QHBoxLayout()
        for label,op in [('New Category','create'),('Rename / Move Category','rename'),('Move Entry','move')]:
            button=QPushButton(label);button.clicked.connect(lambda checked=False,op=op:self.run(lambda:category_action(self,owner.library,op,self.selected_id())));row.addWidget(button)
        root.addLayout(row);buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(self.reject);root.addWidget(buttons)
        self.panel.itemDoubleClicked.connect(lambda item,col:self.owner.place_center(item));self.refresh()

    def selected_id(self):
        item=self.panel.currentItem();return item.data(0,Qt.UserRole) if item else None

    def refresh(self):self.panel.populate(self.owner.library.definitions,self.owner.library);self.owner.refresh_library()
    def run(self,callback):
        try:callback();self.refresh()
        except (ValueError,OSError,KeyError) as error:self.feedback.setText(str(error))

    def selected(self):
        identifier=self.selected_id()
        if not self.owner.library.is_custom(identifier):raise ValueError('Choose a custom definition; built-ins are templates')
        return deepcopy(self.owner.library.definitions[identifier])

    def edit(self):
        from ui.node_wizard import NodeWizard
        definition=self.selected();dialog=NodeWizard(self,definition)
        if dialog.exec()==QDialog.Accepted:self.owner.library.update(dialog.definition)

    def rename(self):
        definition=self.selected();name,ok=QInputDialog.getText(self,'Rename Component','Name',text=definition.name)
        if ok:definition.name=name.strip();self.owner.library.update(definition)

    def delete(self):
        self.selected();self.owner.library.delete(self.selected_id(),self.owner.project)
