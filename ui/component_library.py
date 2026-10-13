from PySide6.QtCore import Qt,QMimeData
from PySide6.QtGui import QDrag
from ui.library_preview import component_icon
from ui.library_browser import LibraryTree,category_paths

MIME_TYPE='application/x-amcad-component'


class ComponentLibraryPanel(LibraryTree):
    library_kind="component"
    def __init__(self):
        super().__init__();self.setDragEnabled(True)
        self.setToolTip('Click to select • double-click to place • right-click for actions')

    def populate(self,definitions,library=None):
        self.begin_refresh(category_paths(library) if library else ['Uncategorized'])
        for definition in definitions.values():
            path=library.category_for(definition) if library else definition.category
            self.add_entry(path,definition.id,f'{definition.name}\n{len(definition.ports)} ports',component_icon(definition),definition.name)
        self.end_refresh()

    def startDrag(self,supportedActions):
        identifier=self.selected_id()
        if not identifier:return
        mime=QMimeData();mime.setData(MIME_TYPE,identifier.encode());mime.setData('application/x-amcad-library-entry',identifier.encode());drag=QDrag(self);drag.setMimeData(mime);drag.exec(Qt.CopyAction|Qt.MoveAction,Qt.CopyAction)
