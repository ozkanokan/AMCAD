from PySide6.QtWidgets import QInputDialog


def category_action(parent,library,operation,entry_id=None):
    if operation=='create':
        path,ok=QInputDialog.getText(parent,'New Category','Nested path (for example Lee/Check Valves)')
        if ok:library.create_category(path)
    elif operation=='move':
        if not entry_id:raise ValueError('Select a library entry')
        path,ok=QInputDialog.getText(parent,'Move Library Entry','Category path',text=library.category_for(library.definitions[entry_id]))
        if ok:library.move_entry(entry_id,path)
    else:
        choices=sorted(library.categories|{library.category_for(d) for d in library.definitions.values()})
        old,ok=QInputDialog.getItem(parent,'Rename / Move Category','Category',choices,editable=False)
        if not ok:return
        new,ok=QInputDialog.getText(parent,'Rename / Move Category','New nested path',text=old)
        if ok:library.rename_category(old,new)
