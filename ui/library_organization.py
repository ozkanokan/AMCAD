from PySide6.QtWidgets import QInputDialog,QMessageBox,QWidget,QHBoxLayout,QComboBox,QToolButton
from ui.library_browser import category_paths


class CategorySelector(QWidget):
    """Choose an existing path, or explicitly create one; no free-text memory needed."""
    def __init__(self,library=None,current='Uncategorized',parent=None):
        super().__init__(parent);self.library=library
        layout=QHBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.combo=QComboBox();layout.addWidget(self.combo,1)
        self.create=QToolButton();self.create.setText('+ New Category');self.create.clicked.connect(self.new_category);layout.addWidget(self.create)
        self.refresh(current)

    def refresh(self,current=None):
        current=current or self.text() or 'Uncategorized'
        paths=set(category_paths(self.library) if self.library else ['Uncategorized','Generic','Valves'])|{current}
        self.combo.clear();self.combo.addItems(sorted(paths,key=str.casefold));self.combo.setCurrentText(current)

    def text(self):return self.combo.currentText()
    def setText(self,value):self.refresh(value)

    def new_category(self):
        path,ok=QInputDialog.getText(self,'New Category','Category path (parent/subcategory)')
        if not ok:return
        try:
            from core.library_categories import LibraryCategories
            path=LibraryCategories.category_path(path)
            if self.library:self.library.create_category(path)
            self.refresh(path)
            owner=self.window().parent()
            if hasattr(owner,'refresh_library'):owner.refresh_library()
            elif hasattr(owner,'refresh'):owner.refresh()
            tree=getattr(owner,'panel',None) if hasattr(self.library,'is_custom') else getattr(getattr(owner,'cavity_panel',None),'tree',None)
            if tree is None and hasattr(self.library,'is_custom'):tree=getattr(owner,'library_panel',None)
            if tree is not None:tree.reveal_category(path)
        except (ValueError,OSError) as error:QMessageBox.warning(self,'Category',str(error))


def category_action(parent,library,operation,entry_id=None,path=None):
    if operation=='create':
        name,ok=QInputDialog.getText(parent,'New Subcategory' if path else 'New Category','Name' if path else 'Category path')
        if ok:
            created=path+'/'+name if path else name;library.create_category(created);return library.category_path(created)
    elif operation=='move':
        if not entry_id:raise ValueError('Select a library entry')
        choices=category_paths(library);current=library.category_for(library.definitions[entry_id])
        target,ok=QInputDialog.getItem(parent,'Move to Category','Category',choices,choices.index(current),editable=False)
        if ok:library.move_entry(entry_id,target);return target
    elif operation=='delete':
        if not path or path=='Uncategorized':raise ValueError('Uncategorized cannot be deleted')
        if QMessageBox.question(parent,'Delete Category',f'Delete {path} and its subcategories? Entries move to Uncategorized; definitions are preserved.',QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes:
            library.delete_category(path)
    else:
        old=path
        if old is None:
            old,ok=QInputDialog.getItem(parent,'Rename Category','Category',category_paths(library),editable=False)
            if not ok:return
        new,ok=QInputDialog.getText(parent,'Rename Category','New category path',text=old)
        if ok:library.rename_category(old,new);return library.category_path(new)


def add_category_menu(menu,parent,library,path,run):
    for text,operation in [('New Subcategory','create'),('Rename','rename'),('Delete','delete')]:
        action=menu.addAction(text);action.setEnabled(path!='Uncategorized' or operation=='create')
        action.triggered.connect(lambda checked=False,op=operation:run(lambda:category_action(parent,library,op,path=path)))
