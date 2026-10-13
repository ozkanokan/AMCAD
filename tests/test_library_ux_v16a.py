"""Category/context/search acceptance workflows, isolated from user libraries."""
from copy import deepcopy
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QColor,QPalette
from PySide6.QtWidgets import QPushButton,QToolButton,QInputDialog,QMessageBox,QGraphicsTextItem,QTableWidget
from PySide6.QtTest import QTest
from core.generic import generic_component
from core.library import ComponentLibrary
from core.cavity_library import CavityLibrary
from core.project import Project
from ui.main_window import MainWindow
from ui.component_manager import ComponentLibraryDialog
from ui.cavity_library import CavityLibraryDialog
from ui.node_wizard import NodeWizard
from ui.cavity_editor import CavityEditor
from test_cavity_library import cavity
from test_cavity_library_ui import close_window,modal


def action(menu,label):return next(a for a in menu.actions() if a.text()==label)
def definition_files(library):return {path.name:path.read_bytes() for path in library.paths.values()}


def test_visible_category_contexts_create_nested_rename_delete_and_restart(qapp,tmp_path,monkeypatch):
    w=MainWindow(tmp_path/'components');d=generic_component(2);w.library.save(d);c=w.cavity_library.save(cavity());w.refresh_library()
    try:
        component_dialog=ComponentLibraryDialog(w);cavity_dialog=CavityLibraryDialog(w)
        for library,tree,menu,refresh in [
            (w.library,component_dialog.panel,component_dialog.actions.menu,component_dialog.refresh),
            (w.cavity_library,cavity_dialog.tree,cavity_dialog.menu,cavity_dialog.refresh)]:
            before=definition_files(library)
            monkeypatch.setattr(QInputDialog,'getText',lambda *args,**kwargs:('Lee',True))
            action(menu(None),'New Category').trigger();assert 'Lee' in tree.paths
            monkeypatch.setattr(QInputDialog,'getText',lambda *args,**kwargs:('Check Valves',True))
            item=tree.paths['Lee'];item.setExpanded(False);action(menu(item),'New Subcategory').trigger();assert 'Lee/Check Valves' in tree.paths and tree.paths['Lee'].isExpanded()
            identifier=d.id if library is w.library else c.id
            library.move_entry(identifier,'Lee/Check Valves');refresh()
            assert next(item for item in tree.entries if item.data(0,Qt.UserRole)==identifier).parent() is tree.paths['Lee/Check Valves']
            monkeypatch.setattr(QInputDialog,'getText',lambda *args,**kwargs:('Manufacturer/Lee',True))
            action(menu(tree.paths['Lee']),'Rename').trigger();assert library.category_for(library.definitions[identifier])=='Manufacturer/Lee/Check Valves'
            assert 'Manufacturer/Lee/Check Valves' in tree.paths
            monkeypatch.setattr(QMessageBox,'question',lambda *args,**kwargs:QMessageBox.Yes)
            action(menu(tree.paths['Manufacturer/Lee']),'Delete').trigger();assert library.category_for(library.definitions[identifier])=='Uncategorized'
            assert 'Manufacturer/Lee/Check Valves' not in tree.paths and definition_files(library)==before
            assert not action(menu(tree.paths['Uncategorized']),'Delete').isEnabled()
            reloaded=type(library)(library.directory);assert reloaded.category_for(reloaded.definitions[identifier])=='Uncategorized'
        component_dialog.reject();cavity_dialog.reject()
    finally:close_window(w)


def test_selectors_component_save_cavity_save_and_preview_contrast(qapp,tmp_path):
    w=MainWindow(tmp_path/'components');w.library.create_category('Lee/Check Valves');w.cavity_library.create_category('Lee/Cavities')
    palette=qapp.palette();dark=QPalette(palette);dark.setColor(QPalette.Text,QColor('white'));qapp.setPalette(dark)
    try:
        wizard=NodeWizard(w);wizard.name.setText('Custom Check');wizard.prefix.setText('CC')
        assert wizard.category.combo.findText('Lee/Check Valves')>=0
        wizard.category.combo.setCurrentText('Lee/Check Valves');wizard.submit();w.library.save(wizard.definition)
        assert ComponentLibrary(w.library.directory).definitions[wizard.definition.id].category=='Lee/Check Valves'
        texts=[item for item in wizard.scene.items() if isinstance(item,QGraphicsTextItem)]
        assert texts and all(item.defaultTextColor()==QColor('#233847') for item in texts)
        c=w.cavity_library.save(cavity());before=definition_files(w.cavity_library)
        editor=CavityEditor(parent=w,cavity_definition=c,cavity_library=w.cavity_library,save_callback=w.save_library_cavity)
        assert editor.category.combo.findText('Lee/Cavities')>=0
        editor.category.combo.setCurrentText('Lee/Cavities');editor.submit()
        assert definition_files(w.cavity_library)==before and w.cavity_library.definitions[c.id].revision==1
        assert CavityLibrary(w.cavity_library.directory).category_for(c)=='Lee/Cavities'
    finally:qapp.setPalette(palette);close_window(w)


def test_move_selectors_drag_signal_search_and_collapsed_state(qapp,tmp_path,monkeypatch):
    w=MainWindow(tmp_path/'components');d=generic_component(2);d.name='Searchable component';w.library.save(d);c=w.cavity_library.save(cavity('Searchable cavity'))
    try:
        for library in (w.library,w.cavity_library):library.create_category('Lee/Valve');library.create_category('Other')
        w.refresh_library();manager=ComponentLibraryDialog(w);cavities=CavityLibraryDialog(w)
        for library,tree,search,menu,refresh,identifier in [
            (w.library,manager.panel,manager.search,manager.actions.menu,manager.refresh,d.id),
            (w.cavity_library,cavities.tree,cavities.search,cavities.menu,cavities.refresh,c.id)]:
            before=definition_files(library);tree.select_id(identifier)
            monkeypatch.setattr(QInputDialog,'getItem',lambda *args,**kwargs:('Lee/Valve',True))
            action(menu(tree.currentItem()),'Move to Category').trigger()
            assert library.category_for(library.definitions[identifier])=='Lee/Valve'
            tree.entry_move_requested.emit(identifier,'Other');assert library.category_for(library.definitions[identifier])=='Other'
            tree.paths['Other'].setExpanded(False);refresh();assert not tree.paths['Other'].isExpanded()
            search.setText('searchable');assert any(not item.isHidden() and item.data(0,Qt.UserRole)==identifier for item in tree.entries)
            search.setText('unmatched-query');assert all(item.isHidden() for item in tree.entries)
            search.clear();assert all(not item.isHidden() for item in tree.entries)
            assert definition_files(library)==before
            assert type(library)(library.directory).category_for(library.definitions[identifier])=='Other'
        manager.reject();cavities.reject()
    finally:close_window(w)


def test_context_actions_applicability_single_creation_and_consistent_docks(qapp,tmp_path):
    w=MainWindow(tmp_path/'components');w.show();qapp.processEvents()
    try:
        component=ComponentLibraryDialog(w);cavities=CavityLibraryDialog(w)
        for dialog,label in [(component,'+ New Component'),(cavities,'+ New Cavity')]:
            creation=[button.text() for button in dialog.findChildren(QPushButton) if button.text()!='Close']
            assert creation==[label]
        assert not cavities.findChildren(QTableWidget)
        builtin=next(item for item in component.panel.entries if item.data(0,Qt.UserRole)=='generic-2');component.panel.setCurrentItem(builtin)
        menu=component.actions.menu(builtin);assert not action(menu,'Edit').isEnabled() and action(menu,'Duplicate').isEnabled()
        assert not action(menu,'Save Selected Instance to Library').isEnabled()
        c=w.cavity_library.save(cavity());cavities.refresh(c.id);menu=cavities.menu(cavities.tree.currentItem())
        assert not action(menu,'Assign to Selected Component').isEnabled() and not action(menu,'Locate in Schematic').isEnabled()
        assert action(menu,'Delete').isEnabled()
        assert type(w.cavity_panel) is not type(cavities.browser) and w.cavity_panel.__class__.__bases__[0] is cavities.browser.__class__
        assert w.component_search.placeholderText()=='Search components…'
        component.reject();cavities.reject()
    finally:close_window(w)


def test_usage_context_locate_remove_and_category_double_click_no_edit(qapp,tmp_path,monkeypatch):
    w=MainWindow(tmp_path/'components');w.place('external-port',0,0);w.place('external-port',200,0);instances=list(w.project.instances.values());c=w.cavity_library.save(cavity())
    for i in instances:w.project.assign_cavity(i.id,c,{'port':c.interfaces[0].id})
    w.record_change();project_before=w.project.to_dict();files=definition_files(w.cavity_library)
    try:
        manager=CavityLibraryDialog(w);manager.show();manager.refresh(c.id);qapp.processEvents()
        assert manager.usages.count()==2;manager.usages.setCurrentRow(1);chosen=manager.usages.currentItem().data(Qt.UserRole)
        menu=manager.menu(manager.tree.currentItem());action(menu,'Locate in Schematic').trigger();assert w.view.selected_instances()==[chosen]
        monkeypatch.setattr(QMessageBox,'question',lambda *args,**kwargs:QMessageBox.No)
        action(menu,'Remove Selected Reference').trigger();assert w.project.to_dict()==project_before
        monkeypatch.setattr(QMessageBox,'question',lambda *args,**kwargs:QMessageBox.Yes)
        action(menu,'Remove Selected Reference').trigger();assert manager.usages.count()==1 and w.project.instances[chosen].cavity_ref is None
        assert definition_files(w.cavity_library)==files and w.project.cavities[c.id].to_dict()==c.to_dict()
        assert not action(manager.menu(manager.tree.currentItem()),'Delete').isEnabled()
        edited=[];monkeypatch.setattr(w,'edit_cavity',lambda identifier:edited.append(identifier))
        category=manager.tree.paths['Uncategorized'];point=manager.tree.visualItemRect(category).center()
        QTest.mouseClick(manager.tree.viewport(),Qt.LeftButton,pos=point);QTest.mouseDClick(manager.tree.viewport(),Qt.LeftButton,pos=point);qapp.processEvents();assert not edited
        manager.tree.select_id(c.id);manager.tree.currentItem().parent().setExpanded(True);manager.tree.scrollToItem(manager.tree.currentItem());qapp.processEvents();point=manager.tree.visualItemRect(manager.tree.currentItem()).center()
        QTest.mouseClick(manager.tree.viewport(),Qt.LeftButton,pos=point);QTest.mouseDClick(manager.tree.viewport(),Qt.LeftButton,pos=point);qapp.processEvents();assert edited==[c.id]
        manager.reject()
        w.save_to(tmp_path/'project.json');reopened=Project.load(tmp_path/'project.json');assert reopened.to_dict()==w.project.to_dict()
    finally:close_window(w)


def test_browser_startup_is_readonly_and_existing_nested_categories_visible(qapp,tmp_path):
    w=MainWindow(tmp_path/'components');d=generic_component(2);w.library.save(d);c=w.cavity_library.save(cavity());w.library.move_entry(d.id,'Lee/Check');w.cavity_library.move_entry(c.id,'Lee/Check');w.cavity_library.move_entry(c.id,'__in_use__')
    component_data={p.name:p.read_bytes() for p in w.library.directory.iterdir()};cavity_data={p.name:p.read_bytes() for p in w.cavity_library.directory.iterdir()};close_window(w)
    restarted=MainWindow(tmp_path/'components')
    try:
        assert 'Lee/Check' in restarted.library_panel.paths and 'Lee/Check' in restarted.cavity_panel.tree.paths
        assert restarted.cavity_panel.tree.paths['__in_use__'].text(0)=='__in_use__'
        entry=next(item for item in restarted.cavity_panel.tree.entries if item.data(0,Qt.UserRole)==c.id)
        assert entry.parent() is restarted.cavity_panel.tree.paths['__in_use__']
        ComponentLibraryDialog(restarted).reject();CavityLibraryDialog(restarted).reject()
        assert component_data=={p.name:p.read_bytes() for p in restarted.library.directory.iterdir()}
        assert cavity_data=={p.name:p.read_bytes() for p in restarted.cavity_library.directory.iterdir()}
    finally:close_window(restarted)


def test_selector_new_category_and_category_only_component_edit_preserve_revision(qapp,tmp_path,monkeypatch):
    w=MainWindow(tmp_path/'components');d=generic_component(2);d.component_cad_path='archived-model.3dm';d.ports[0].local_position_xyz=[1,2,3];d.ports[0].local_direction_xyz=[0,0,1];w.library.save(d);w.library.move_entry(d.id,'Lee/Old');w.library.create_category('Lee/New');w.refresh_library()
    try:
        wizard=NodeWizard(w);monkeypatch.setattr(QInputDialog,'getText',lambda *args,**kwargs:('Created/From Wizard',True));wizard.category.create.click()
        assert wizard.category.text()=='Created/From Wizard' and 'Created/From Wizard' in w.library_panel.paths
        before=definition_files(w.library);manager=ComponentLibraryDialog(w);manager.panel.select_id(d.id)
        def select(dialog):
            assert dialog.category.text()=='Lee/Old';dialog.category.combo.setCurrentText('Lee/New');dialog.submit()
        modal(manager.actions.edit,select);manager.refresh()
        assert definition_files(w.library)==before and w.library.definitions[d.id].revision==1
        assert ComponentLibrary(w.library.directory).category_for(d)=='Lee/New'
        wizard.reject();manager.reject()
    finally:close_window(w)


def test_category_drop_routes_metadata_and_rejects_cross_library(qapp,tmp_path):
    from PySide6.QtCore import QMimeData,QPointF
    w=MainWindow(tmp_path/'components');d=generic_component(2);w.library.save(d);w.library.create_category('Target');c=w.cavity_library.save(cavity());w.refresh_library();w.show();qapp.processEvents()
    class Drop:
        def __init__(self,source,identifier,target):
            self.source_tree=source;self.target=target;self.mime=QMimeData();self.mime.setData('application/x-amcad-library-entry',identifier.encode());self.accepted=False
        def source(self):return self.source_tree
        def mimeData(self):return self.mime
        def position(self):return QPointF(self.target)
        def acceptProposedAction(self):self.accepted=True
        def ignore(self):self.accepted=False
    try:
        tree=w.library_panel;target=tree.visualItemRect(tree.paths['Target']).center();before=definition_files(w.library)
        drop=Drop(tree,d.id,target);tree.dropEvent(drop)
        assert drop.accepted and w.library.category_for(d)=='Target' and definition_files(w.library)==before
        wrong=Drop(w.cavity_panel.tree,c.id,target);tree.dropEvent(wrong);assert not wrong.accepted
    finally:close_window(w)
