"""Qt workflows for independent creation, library management and instance assignment."""
from copy import deepcopy
from pathlib import Path
import pytest
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QApplication,QLabel
from core.cavity_library import CavityLibrary
from core.project import Project
from core.history import ProjectHistory
from core.cavity_surface import surface_patches
from ui.main_window import MainWindow
from ui.cavity_editor import CavityEditor,InterfaceDialog
from ui.cavity_library import CavityLibraryDialog,PortMappingDialog
from test_cavity_library import cavity,component,mapping


def modal(action,callback):
    errors=[]
    def run():
        dialog=QApplication.activeModalWidget()
        try:callback(dialog)
        except Exception as error:
            errors.append(error)
            if dialog:dialog.reject()
    QTimer.singleShot(0,run);result=action()
    if errors:raise errors[0]
    return result


def close_window(window):
    window.history.mark_saved(window.project);window.close()


def test_main_menus_independent_new_cavity_requires_name_and_restart(qapp,tmp_path):
    w=MainWindow(tmp_path/'components');w.show();qapp.processEvents()
    try:
        assert [action.text().replace('&','') for action in w.menuBar().actions()]==['File','Edit','Component','Cavity','View']
        assert not w.view.selected_instances()
        def fill(e):
            assert isinstance(e,CavityEditor) and e.independent and len(e.profile.vertices)==2
            e.profile.vertices=deepcopy(cavity(count=0).profile.vertices);e.view.rebuild();e.profile_changed()
            e.submit();assert e.result_cavity is None and 'name' in e.feedback.text()
            e.cavity_name.setText('Independent test cavity');e.submit()
        saved=modal(w.new_cavity,fill)
        assert saved and saved.port_count==0 and saved.revision==1 and not w.project.definitions
        assert CavityLibrary(w.cavity_library.directory).definitions[saved.id].name=='Independent test cavity'
        modal(w.open_cavity_library,lambda d:(isinstance(d,CavityLibraryDialog) or pytest.fail(),d.reject()))
    finally:close_window(w)


def test_independent_editor_adds_interfaces_without_schematic_ports(qapp,tmp_path):
    lib=CavityLibrary(tmp_path);e=CavityEditor(cavity_library=lib);e.show();qapp.processEvents()
    try:
        e.profile.vertices=deepcopy(cavity(count=0).profile.vertices);e.view.rebuild();e.profile_changed()
        a=surface_patches(e.profile)[2].anchor
        for _ in range(2):
            e.begin_surface_port();assert e.surface_place_mode
            def accept(d):
                assert isinstance(d,InterfaceDialog) and d.port.count()==1
                d.submit()
            modal(lambda:e.place_surface_port(a),accept)
        assert len(e.interfaces)==2 and len({m.id for m in e.interfaces})==2
        assert all(m.id==m.hydraulic_port_id for m in e.interfaces)
        assert e.view.marker_labels[e.interfaces[0].id].text()=='Interface 1'
        e.cavity_name.setText('Two interfaces');e.submit()
        assert e.result()==QDialog.Accepted and e.result_cavity.port_count==2
        assert CavityLibrary(tmp_path).definitions[e.result_cavity.id].port_count==2
    finally:e.reject()


def test_library_instance_assignment_independent_replacement_and_remove(qapp,tmp_path):
    w=MainWindow(tmp_path/'components');w.show();qapp.processEvents()
    try:
        w.place('external-port',0,0);w.place('external-port',200,0)
        a,b=list(w.project.instances.values());w.project.rename(a.id,'R');w.project.rename(b.id,'RET');w.record_change()
        ca=w.cavity_library.save(cavity('A'));cb=w.cavity_library.save(cavity('B'))
        for i,c in ((a,ca),(b,cb)):
            manager=CavityLibraryDialog(w,i.id);manager.refresh(c.id)
            modal(manager.assign,lambda d:d.submit())
            assert w.project.instances[i.id].cavity_ref==c.id
            manager.reject()
        assert a.cavity_ref!=b.cavity_ref
        manager=CavityLibraryDialog(w,b.id);manager.refresh(ca.id);modal(manager.assign,lambda d:d.submit())
        assert a.cavity_ref==b.cavity_ref==ca.id and len(w.project.cavity_usage(ca.id))==2
        manager.delete();assert 'used' in manager.feedback.text() and ca.id in w.cavity_library.definitions
        manager.remove_assignment();assert b.cavity_ref is None and a.cavity_ref==ca.id
        assert w.project.definitions[a.definition_id].physical.cavity_type=='NONE'
        w.save_to(tmp_path/'project.json');loaded=Project.load(tmp_path/'project.json')
        assert loaded.instances[a.id].cavity_ref==ca.id and loaded.instances[b.id].cavity_ref is None
        manager.reject()
    finally:close_window(w)


def test_ambiguous_mapping_requires_explicit_selection(qapp,tmp_path):
    w=MainWindow(tmp_path/'components');d=component(2);i=w.project.add_instance(d);w.view.rebuild();w.record_change()
    c=w.cavity_library.save(cavity(count=2));manager=CavityLibraryDialog(w,i.id);manager.refresh(c.id)
    try:
        def choose(dialog):
            assert isinstance(dialog,PortMappingDialog)
            assert all(field.currentData() is None for field in dialog.controls.values())
            dialog.submit();assert dialog.mapping is None
            fields=list(dialog.controls.values());fields[0].setCurrentIndex(1);fields[1].setCurrentIndex(1)
            dialog.submit();assert 'one-to-one' in dialog.feedback.text()
            fields[1].setCurrentIndex(2);dialog.submit()
        modal(manager.assign,choose)
        assert i.port_mapping==mapping(c)
        incompatible=w.cavity_library.save(cavity('Wrong count',1));manager.refresh()
        assert incompatible.id not in [manager.table.item(r,0).data(Qt.UserRole) for r in range(manager.table.rowCount())]
    finally:manager.reject();close_window(w)


def test_shared_edit_warning_save_as_new_and_undo_redo(qapp,tmp_path):
    w=MainWindow(tmp_path/'components');d=component();a=w.project.add_instance(d);b=w.project.add_instance(d,x=200)
    c=w.cavity_library.save(cavity());w.project.assign_cavity(a.id,c,mapping(c));w.project.assign_cavity(b.id,c,mapping(c));w.view.rebuild();w.record_change()
    try:
        def edit(e):
            assert any('Shared cavity' in label.text() and a.name in label.text() and b.name in label.text() for label in e.findChildren(QLabel))
            e.cavity_description.setText('Shared update');e.submit()
        saved=modal(lambda:w.edit_cavity(c.id),edit)
        assert saved.revision==2 and w.project.cavities[c.id].description=='Shared update'
        w.undo();assert w.project.cavities[c.id].revision==1 and w.cavity_library.definitions[c.id].revision==2
        w.redo();assert w.project.cavities[c.id].revision==2
        original=deepcopy(w.cavity_library.definitions[c.id].to_dict())
        def save_new(e):
            e.cavity_name.setText('Separate copy');e.submit(save_as_new=True)
        copy=modal(lambda:w.edit_cavity(c.id),save_new)
        assert copy.id!=c.id and copy.revision==1 and w.cavity_library.definitions[c.id].to_dict()==original
        assert all(i.cavity_ref==c.id for i in w.project.instances.values())
        assert {m.id for m in copy.interfaces}.isdisjoint(m.id for m in c.interfaces)
    finally:close_window(w)


def test_missing_library_snapshot_editor_requires_save_as_new(qapp,tmp_path):
    w=MainWindow(tmp_path/'components');i=w.project.add_instance(component());c=cavity();c.revision=3
    w.project.assign_cavity(i.id,c,mapping(c));w.view.rebuild();w.record_change()
    try:
        def save(e):
            assert any('Missing library' in label.text() for label in e.findChildren(QLabel))
            e.submit();assert e.result_cavity is None and 'Save As New' in e.feedback.text()
            e.submit(save_as_new=True)
        new=modal(lambda:w.edit_cavity(c.id),save)
        assert new.id!=c.id and new.revision==1 and i.cavity_ref==c.id
        assert w.project.cavities[c.id].revision==3
    finally:close_window(w)


def test_legacy_import_ui_keeps_assignment_explicit(qapp,tmp_path,monkeypatch):
    from examples.create_physical_demo import check_valve_definition
    w=MainWindow(tmp_path/'components');i=w.project.add_instance(check_valve_definition());w.view.rebuild();w.record_change()
    manager=CavityLibraryDialog(w,i.id)
    try:
        original=w.project.to_dict();manager.import_legacy()
        assert len(w.cavity_library.definitions)==1 and w.project.to_dict()==original
        assert 'unchanged' in manager.feedback.text()
        assert manager.table.rowCount()==1 and 'INVALID' in manager.table.item(0,5).text()
        manager.import_legacy();assert len(w.cavity_library.definitions)==1
        original_id=manager.selected_id();manager.duplicate();copy_id=manager.selected_id()
        assert copy_id!=original_id and len(w.cavity_library.definitions)==2
        from PySide6.QtWidgets import QInputDialog
        monkeypatch.setattr(QInputDialog,'getText',lambda *a,**k:('Renamed imported draft',True))
        manager.rename();assert w.cavity_library.definitions[copy_id].name=='Renamed imported draft'
        assert 'INVALID' in manager.table.item(manager.table.currentRow(),5).text()
    finally:manager.reject();close_window(w)


def test_shared_invalid_edit_rejected_before_library_write(qapp,tmp_path):
    w=MainWindow(tmp_path/'components');i=w.project.add_instance(component());c=w.cavity_library.save(cavity());w.project.assign_cavity(i.id,c,mapping(c));w.record_change()
    before=w.cavity_library.paths[c.id].read_text();project=w.project.to_dict()
    try:
        edited=deepcopy(c);edited.interfaces=[]
        with pytest.raises(ValueError):w.save_library_cavity(edited)
        assert w.cavity_library.paths[c.id].read_text()==before and w.project.to_dict()==project
    finally:close_window(w)


def test_library_rename_duplicate_and_explicit_snapshot_refresh(qapp,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    w=MainWindow(tmp_path/'components');i=w.project.add_instance(component());c=w.cavity_library.save(cavity());w.project.assign_cavity(i.id,c,mapping(c));w.record_change()
    d=CavityLibraryDialog(w,i.id);d.refresh(c.id)
    try:
        monkeypatch.setattr(QInputDialog,'getText',lambda *args,**kwargs:('Renamed cavity',True))
        d.rename();assert w.cavity_library.definitions[c.id].name=='Renamed cavity' and w.project.cavities[c.id].revision==2
        d.duplicate();copy_id=d.selected_id();assert copy_id!=c.id and w.cavity_library.definitions[copy_id].revision==1
        changed=deepcopy(w.cavity_library.definitions[c.id]);changed.description='Library update only';new=w.cavity_library.save(changed)
        assert w.project.cavities[c.id].revision==2
        d.refresh(c.id);assert 'explicit refresh' in d.table.item(d.table.currentRow(),5).text()
        d.refresh_snapshot();assert w.project.cavities[c.id].revision==new.revision
    finally:d.reject();close_window(w)


def test_properties_assignment_action_is_instance_specific(qapp,tmp_path):
    from PySide6.QtWidgets import QPushButton
    w=MainWindow(tmp_path/'components');i=w.project.add_instance(component());w.view.rebuild();w.record_change();called=[]
    w.assign_cavity=lambda instance_id:called.append(instance_id)
    try:
        def inspect(dialog):
            button=next(b for b in dialog.findChildren(QPushButton) if b.text()=='Assign Cavity…')
            button.click();assert called==[i.id];dialog.reject()
        modal(lambda:w.properties(i.id),inspect)
    finally:close_window(w)


def test_create_new_cavity_and_assign_after_save(qapp,tmp_path,monkeypatch):
    w=MainWindow(tmp_path/'components');i=w.project.add_instance(component());w.view.rebuild();w.record_change()
    manager=CavityLibraryDialog(w,i.id)
    # Mapping-dialog mouse/selection validation is tested above. Here automate only
    # its modal entry to verify the two-dialog New -> Save -> Assign composition.
    def accept_mapping(dialog):
        dialog.submit();return dialog.result()
    monkeypatch.setattr(PortMappingDialog,'exec',accept_mapping)
    try:
        def fill(e):
            sample=cavity('New assigned')
            e.profile.vertices=deepcopy(sample.profile.vertices);e.interfaces.extend(deepcopy(sample.interfaces))
            e.view.rebuild();e.profile_changed();e.cavity_name.setText('New assigned');e.submit()
        modal(manager.new,fill)
        assert i.cavity_ref is not None
        assert w.cavity_library.definitions[i.cavity_ref].name=='New assigned'
        assert len(i.port_mapping)==1 and w.project.cavities[i.cavity_ref].revision==1
    finally:manager.reject();close_window(w)
