from PySide6.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView
from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QDrag

MIME_TYPE = 'application/x-amcad-component'


class ComponentLibraryPanel(QListWidget):
    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSpacing(5)
        self.setToolTip('Drag a component onto the canvas, or double-click to place it at the view center')

    def populate(self, definitions):
        self.clear()
        for definition in definitions.values():
            item = QListWidgetItem(f'{definition.name}\n{definition.category} · {len(definition.ports)} port(s)')
            item.setData(Qt.UserRole,definition.id)
            item.setToolTip(definition.name)
            self.addItem(item)

    def startDrag(self, supportedActions):
        if not self.currentItem(): return
        mime = QMimeData()
        mime.setData(MIME_TYPE,self.currentItem().data(Qt.UserRole).encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)
