from PySide6.QtCore import Qt,QSize
from PySide6.QtWidgets import QWidget,QVBoxLayout,QTreeWidget,QTreeWidgetItem,QPushButton,QInputDialog
from ui.component_library import category_item
from ui.library_preview import cavity_icon


class CavityLibraryPanel(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;root=QVBoxLayout(self)
        self.tree=QTreeWidget();self.tree.setHeaderHidden(True);self.tree.setIconSize(QSize(100,65));root.addWidget(self.tree)
        for label,callback in [('Locate in Schematic',self.locate),('Cavity Library…',owner.open_cavity_library),('+ New Cavity',owner.new_cavity)]:
            button=QPushButton(label);button.clicked.connect(callback);root.addWidget(button)
        self.tree.itemDoubleClicked.connect(lambda item,col:owner.edit_cavity(item.data(0,Qt.UserRole)) if item.data(0,Qt.UserRole) else None)

    def refresh(self):
        tree=self.tree;tree.clear();owner=self.owner
        used=QTreeWidgetItem(['In Use']);tree.addTopLevelItem(used);used.setExpanded(True)
        for cavity in owner.project.cavities.values():
            instances=owner.project.cavity_usage(cavity.id)
            item=QTreeWidgetItem([f'{cavity.name} · {len(instances)} uses\n'+', '.join(i.name for i in instances)])
            item.setData(0,Qt.UserRole,cavity.id);item.setIcon(0,cavity_icon(cavity));used.addChild(item)
        paths={}
        for path in sorted(owner.cavity_library.categories):category_item(tree,paths,'Library/'+path)
        for cavity in owner.cavity_library.definitions.values():
            parent=category_item(tree,paths,'Library/'+owner.cavity_library.category_for(cavity))
            item=QTreeWidgetItem([cavity.name]);item.setData(0,Qt.UserRole,cavity.id);item.setIcon(0,cavity_icon(cavity));parent.addChild(item)

    def locate(self):
        item=self.tree.currentItem()
        if item:self.owner.locate_cavity(item.data(0,Qt.UserRole))
