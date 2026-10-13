"""Shared category browsing and search, with stable IDs separate from display text."""
from PySide6.QtCore import Qt,QSize,QMimeData,Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QTreeWidget,QTreeWidgetItem

ID_ROLE=Qt.UserRole
CATEGORY_ROLE=Qt.UserRole+1


def category_paths(library):
    paths={'Uncategorized'}|set(library.categories)|{library.category_for(d) for d in library.definitions.values()}
    return sorted(paths,key=str.casefold)


class LibraryTree(QTreeWidget):
    entry_move_requested=Signal(str,str)
    library_kind=None
    def __init__(self):
        super().__init__();self.setHeaderHidden(True);self.setIconSize(QSize(110,70))
        self.setUniformRowHeights(False);self.entries=[];self.paths={};self.query=''
        self.setContextMenuPolicy(Qt.CustomContextMenu);self.setDragEnabled(True);self.setAcceptDrops(True);self.setDropIndicatorShown(True)

    def category(self,path):
        parent=None;parts=[]
        for part in path.split('/'):
            parts.append(part);key='/'.join(parts)
            if key not in self.paths:
                item=QTreeWidgetItem([part]);item.setData(0,CATEGORY_ROLE,key)
                if parent:parent.addChild(item)
                else:self.addTopLevelItem(item)
                self.paths[key]=item;item.setExpanded(True)
            parent=self.paths[key]
        return parent

    def begin_refresh(self,paths):
        self.saved_id=self.selected_id();self.collapsed={path for path,item in self.paths.items() if not item.isExpanded()}
        self.blockSignals(True);self.clear();self.entries=[];self.paths={}
        for path in paths:self.category(path)

    def add_entry(self,path,identifier,text,icon,tooltip=''):
        item=QTreeWidgetItem([text]);item.setData(0,ID_ROLE,identifier);item.setIcon(0,icon);item.setToolTip(0,tooltip)
        parent=path if isinstance(path,QTreeWidgetItem) else self.category(path)
        parent.addChild(item);self.entries.append(item);return item

    def end_refresh(self,selected=None):
        for path in self.collapsed:
            if path in self.paths:self.paths[path].setExpanded(False)
        self.select_id(selected or self.saved_id)
        self.blockSignals(False);self.filter(self.query)

    def select_id(self,identifier):
        item=next((item for item in self.entries if item.data(0,ID_ROLE)==identifier),None)
        if item:self.setCurrentItem(item)

    def reveal_category(self,path):
        item=self.paths.get(path)
        if item is None:return
        parent=item
        while parent:
            parent.setExpanded(True);parent=parent.parent()
        self.scrollToItem(item)

    def selected_id(self):
        item=self.currentItem();return item.data(0,ID_ROLE) if item else None

    def filter(self,text):
        self.query=text;query=text.strip().casefold()
        def visit(item,ancestor_matches=False):
            match=ancestor_matches or query in item.text(0).casefold()
            children=[visit(item.child(i),match) for i in range(item.childCount())]
            visible=not query or match or any(children);item.setHidden(not visible)
            if query and any(children):item.setExpanded(True)
            return visible
        for i in range(self.topLevelItemCount()):visit(self.topLevelItem(i))
        if self.currentItem() and self.currentItem().isHidden():self.clearSelection();self.setCurrentItem(None)

    def count(self):return len(self.entries)
    def item(self,index):return self.entries[index]

    def startDrag(self,supportedActions):
        identifier=self.selected_id()
        if not identifier:return
        mime=QMimeData();mime.setData('application/x-amcad-library-entry',identifier.encode())
        drag=QDrag(self);drag.setMimeData(mime);drag.exec(Qt.MoveAction)

    def valid_drag(self,event):
        source=event.source()
        return isinstance(source,LibraryTree) and source.library_kind==self.library_kind and event.mimeData().hasFormat('application/x-amcad-library-entry')

    def dragEnterEvent(self,event):
        if self.valid_drag(event):event.acceptProposedAction()
        else:event.ignore()

    def dragMoveEvent(self,event):
        item=self.itemAt(event.position().toPoint())
        if self.valid_drag(event) and item and item.data(0,CATEGORY_ROLE):event.acceptProposedAction()
        else:event.ignore()

    def dropEvent(self,event):
        item=self.itemAt(event.position().toPoint());path=item.data(0,CATEGORY_ROLE) if item else None
        if self.valid_drag(event) and path:
            identifier=bytes(event.mimeData().data('application/x-amcad-library-entry')).decode()
            self.entry_move_requested.emit(identifier,path);self.reveal_category(path);event.acceptProposedAction()
        else:event.ignore()
