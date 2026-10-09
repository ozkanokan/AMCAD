from PySide6.QtWidgets import QTreeWidget,QTreeWidgetItem,QAbstractItemView
from PySide6.QtCore import Qt,QMimeData,QSize
from PySide6.QtGui import QDrag
from ui.library_preview import component_icon

MIME_TYPE='application/x-amcad-component'


def category_item(tree,paths,path):
    parent=None;parts=[]
    for part in path.split('/'):
        parts.append(part);key='/'.join(parts)
        if key not in paths:
            item=QTreeWidgetItem([part]);item.setData(0,Qt.UserRole+1,key)
            if parent:parent.addChild(item)
            else:tree.addTopLevelItem(item)
            paths[key]=item;item.setExpanded(True)
        parent=paths[key]
    return parent


class ComponentLibraryPanel(QTreeWidget):
    def __init__(self):
        super().__init__();self.setHeaderHidden(True);self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection);self.setIconSize(QSize(100,65));self.entries=[]
        self.setToolTip('Drag a symbol onto the schematic, or double-click to place it')

    def populate(self,definitions,library=None):
        self.clear();self.entries=[];paths={}
        if library:
            for path in sorted(library.categories):category_item(self,paths,path)
        for definition in definitions.values():
            path=library.category_for(definition) if library else definition.category
            parent=category_item(self,paths,path)
            item=QTreeWidgetItem([f'{definition.name} · {len(definition.ports)} ports'])
            item.setData(0,Qt.UserRole,definition.id);item.setIcon(0,component_icon(definition));item.setToolTip(0,definition.name)
            parent.addChild(item);self.entries.append(item)

    def count(self):return len(self.entries)
    def item(self,index):return self.entries[index]

    def startDrag(self,supportedActions):
        item=self.currentItem();identifier=item.data(0,Qt.UserRole) if item else None
        if not identifier:return
        mime=QMimeData();mime.setData(MIME_TYPE,identifier.encode());drag=QDrag(self);drag.setMimeData(mime);drag.exec(Qt.CopyAction)
