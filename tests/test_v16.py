"""V1.6 libraries, identity preservation and actual Qt workflows, all isolated."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from PySide6.QtCore import Qt,QPointF
from PySide6.QtWidgets import QDialog,QDialogButtonBox,QTableWidget,QLabel,QPushButton,QMessageBox,QInputDialog
from core.generic import generic_component
from core.project import Project
from core.library import ComponentLibrary
from core.cavity_library import CavityLibrary
from core.line_geometry import endpoint
from core.symbol_layout import symbol_dimensions
from core.graph import export_graph
from ui.main_window import MainWindow
from ui.cavity_library import PortMappingDialog,CavityLibraryDialog
from ui.component_manager import ComponentLibraryDialog
from ui.library_preview import component_icon,cavity_icon
from test_cavity_library import cavity,mapping
from test_cavity_library_ui import modal,close_window


@pytest.mark.parametrize('count',[1,2,3,4,5,10,20,32])
def test_generic_counts(count):
    definition=generic_component(count);p=Project();a=p.add_instance(definition);b=p.add_instance(definition)
    assert [port.display_name for port in definition.ports]==[f'Port {i+1}' for i in range(count)]
    names={definition.ports[0].id:'Supply'};sides={definition.ports[0].id:'BOTTOM'}
    p.configure_ports(a.id,names,sides);assert p.effective_definition(b.id)==definition
    assert len(p.nodes)==count*2;p.validate()
    assert Project.from_dict(p.to_dict()).instances[a.id].port_names==names


def test_resize_is_independent_and_preserves_connections(tmp_path):
    p=Project();d=generic_component(2);d.name='Custom generic';d.prefix='CG';d.category='Lee/Generic';a=p.add_instance(d);b=p.add_instance(d,500,0)
    source=p.node_for(a.id,'p1');target=p.node_for(b.id,'p1');connection=p.connect(source.id,target.id)
    p.resize_generic(a.id,20)
    resized=p.effective_definition(a.id);assert (resized.name,resized.prefix,resized.category)==(d.name,d.prefix,d.category)
    assert p.node_for(a.id,'p1').id==source.id and len(p.effective_definition(b.id).ports)==2
    assert connection.from_port_id=='p1';p.validate()
    p.connect(p.node_for(a.id,'p20').id,p.node_for(b.id,'p2').id)
    before=p.to_dict()
    with pytest.raises(ValueError,match='Disconnect'):p.resize_generic(a.id,2)
    assert p.to_dict()==before
    loaded=Project.from_dict(p.to_dict());assert len(loaded.effective_definition(a.id).ports)==20


@pytest.mark.parametrize('definition_id',['external-port','generic-2','generic-4','junction-3'])
def test_label_side_edits_preserve_identity_mapping_and_copy(tmp_path,definition_id):
    library=ComponentLibrary(tmp_path/'components');p=Project();d=library.definitions[definition_id]
    a=p.add_instance(d);b=p.add_instance(library.definitions['external-port'],500,0)
    port=d.ports[0];node=p.node_for(a.id,port.id);connection=p.connect(node.id,p.node_for(b.id,'port').id)
    ids=(a.id,node.id,connection.id,connection.from_port_id)
    names={port.id:'Long readable hydraulic supply'}
    # Junction sides remain distinct: label edits work, swapping edges must be atomic.
    sides={port.id:'BOTTOM'} if definition_id!='junction-3' else {p.id:p.side for p in d.ports}
    p.configure_ports(a.id,names,sides);p.rotate(a.id);p.validate()
    assert ids==(a.id,node.id,connection.id,connection.from_port_id)
    c=cavity(count=len(d.ports));p.assign_cavity(a.id,c,{p.id:m.id for p,m in zip(d.ports,c.interfaces)});saved_mapping=deepcopy(a.port_mapping)
    p.configure_ports(a.id,{port.id:'Renamed again'},sides);assert a.port_mapping==saved_mapping
    copied=p.paste_subgraph(p.copy_subgraph([a.id]))[0]
    assert p.instances[copied].port_names==a.port_names and p.instances[copied].port_sides==a.port_sides
    assert export_graph(p)['nodes'][0]['label'].endswith('Renamed again') or definition_id=='external-port'
    p.validate()


def test_component_library_revisions_categories_and_defaults(tmp_path):
    library=ComponentLibrary(tmp_path/'components');d=generic_component(2);c=cavity(count=2)
    d.default_cavity_ref=c.id;d.default_port_mapping={p.id:m.id for p,m in zip(d.ports,c.interfaces)};library.save(d)
    library.create_category('Lee/Check Valves');library.move_entry(d.id,'Lee/Check Valves')
    original=library.paths[d.id].read_bytes();library.rename_category('Lee','LEE')
    assert library.paths[d.id].read_bytes()==original
    d.name='Revised';library.update(d);assert library.definitions[d.id].revision==2
    reloaded=ComponentLibrary(library.directory);assert reloaded.category_for(reloaded.definitions[d.id])=='LEE/Check Valves'
    assert reloaded.definitions[d.id].default_cavity_ref==c.id
    assert 'vertices' not in library.paths[d.id].read_text()
    p=Project();p.add_instance(reloaded.definitions[d.id]);p.validate()
    with pytest.raises(ValueError,match='used'):reloaded.delete(d.id,p)
    reloaded.delete(d.id,Project());assert d.id not in ComponentLibrary(library.directory).definitions


def test_library_startup_and_category_changes_do_not_touch_cavities(tmp_path):
    library=CavityLibrary(tmp_path/'cavities');c=library.save(cavity())
    original={path.name:path.read_bytes() for path in library.directory.iterdir()}
    reloaded=CavityLibrary(library.directory);assert not reloaded.errors
    assert original=={path.name:path.read_bytes() for path in library.directory.iterdir()}
    reloaded.create_category('Lee/Check Valves');reloaded.move_entry(c.id,'Lee/Check Valves');reloaded.rename_category('Lee','Manufacturer/Lee')
    assert all((library.directory/name).read_bytes()==data for name,data in original.items())
    final=CavityLibrary(library.directory);assert final.definitions[c.id].to_dict()==c.to_dict()
    assert final.category_for(c)=='Manufacturer/Lee/Check Valves' and not final.errors


@pytest.mark.parametrize('count',[1,2,20])
def test_mapping_dialog_requires_explicit_complete_unique_selection(qapp,count):
    d=generic_component(count);c=cavity(count=1)
    from core.port import new_id
    for i in range(1,count):
        marker=deepcopy(c.interfaces[0]);marker.id=new_id();marker.hydraulic_port_id=marker.id;marker.surface_anchor.t=.2+.6*i/count;c.interfaces.append(marker)
    c.validate();dialog=PortMappingDialog(d,c)
    assert all(control.currentData() is None for control in dialog.controls.values())
    assert all(c.id not in label.text() for label in dialog.findChildren(QLabel))
    dialog.submit();assert dialog.mapping is None
    for index,control in enumerate(dialog.controls.values()):control.setCurrentIndex(index+1)
    dialog.submit();assert dialog.result()==QDialog.Accepted and len(dialog.mapping)==count


def test_docks_menus_toolbar_visibility_and_thumbnails(qapp,tmp_path):
    w=MainWindow(tmp_path/'components');w.show();qapp.processEvents()
    try:
        menus={a.text().replace('&',''):a.menu() for a in w.menuBar().actions()}
        assert [a.text() for a in menus['Component'].actions()]==['New Component…','Component Library…']
        assert [a.text() for a in menus['Cavity'].actions()]==['New Cavity…','Cavity Library…']
        assert [a.text() for a in menus['View'].actions()]==['Component Library','Cavity Library','Fit Schematic']
        from PySide6.QtWidgets import QToolBar
        assert [a.text() for a in w.findChild(QToolBar).actions()]==['Save','Undo','Redo','Delete Selection','Fit Schematic']
        original=w.project.to_dict()
        for dock in (w.component_dock,w.cavity_dock):
            dock.show();qapp.processEvents();dock.close();qapp.processEvents();assert not dock.toggleViewAction().isChecked()
            dock.toggleViewAction().trigger();qapp.processEvents();assert dock.toggleViewAction().isChecked()
        assert w.project.to_dict()==original
        assert not component_icon(generic_component(20)).isNull() and not cavity_icon(cavity()).isNull()
    finally:close_window(w)


def test_properties_assignment_refresh_and_accept_preserve_mapping(qapp,tmp_path,monkeypatch):
    w=MainWindow(tmp_path/'components');w.place('external-port',0,0);iid=next(iter(w.project.instances));c=w.cavity_library.save(cavity())
    def assign(instance_id):w.project.assign_cavity(instance_id,c,{'port':c.interfaces[0].id});w.record_change()
    monkeypatch.setattr(w,'assign_cavity',assign)
    try:
        def edit(dialog):
            status=dialog.findChild(QLabel,'cavityAssignmentStatus');assert status.text()=='Unassigned'
            buttons={b.text():b for b in dialog.findChildren(QPushButton)}
            assert not buttons['Remove Cavity Assignment'].isEnabled()
            buttons['Assign Cavity…'].click();assert c.name in status.text() and buttons['Remove Cavity Assignment'].isEnabled()
            table=dialog.findChild(QTableWidget,'instancePorts');table.item(0,0).setText('Supply')
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
        modal(lambda:w.properties(iid),edit)
        assert w.project.instances[iid].cavity_ref==c.id and w.project.instances[iid].port_mapping=={'port':c.interfaces[0].id}
        assert w.project.instances[iid].port_names=={'port':'Supply'}
        def remove(dialog):
            next(b for b in dialog.findChildren(QPushButton) if b.text()=='Remove Cavity Assignment').click()
            assert dialog.findChild(QLabel,'cavityAssignmentStatus').text()=='Unassigned';dialog.reject()
        modal(lambda:w.properties(iid),remove)
        assert w.project.instances[iid].cavity_ref is None and c.id in w.cavity_library.definitions
    finally:close_window(w)


def test_assignment_autoclose_current_selection_usage_locate_and_global_remove(qapp,tmp_path,monkeypatch):
    w=MainWindow(tmp_path/'components');w.place('external-port',0,0);w.place('external-port',300,0)
    a,b=w.project.instances.values();c=w.cavity_library.save(cavity())
    try:
        for instance in (a,b):
            manager=CavityLibraryDialog(w,instance.id);manager.refresh(c.id)
            modal(manager.assign,lambda d:(next(iter(d.controls.values())).setCurrentIndex(1),d.submit()))
            assert manager.result()==QDialog.Accepted
        manager=CavityLibraryDialog(w,b.id);assert manager.selected_id()==c.id;assert manager.usages.count()==2
        assert {manager.usages.item(i).text() for i in range(2)}=={a.name,b.name}
        manager.usages.setCurrentRow(1);chosen=manager.usages.currentItem().data(Qt.UserRole);manager.locate()
        assert w.view.selected_instances()==[chosen]
        monkeypatch.setattr(QMessageBox,'question',lambda *args,**kwargs:QMessageBox.Yes)
        manager.remove_reference();assert manager.usages.count()==1 and w.project.instances[chosen].cavity_ref is None
        assert c.id in w.cavity_library.definitions and w.history.is_dirty(w.project)
        manager.reject()
    finally:close_window(w)


def test_saved_component_inherits_default_independently(qapp,tmp_path,monkeypatch):
    w=MainWindow(tmp_path/'components');d=generic_component(1);c=w.cavity_library.save(cavity());d.default_cavity_ref=c.id;d.default_port_mapping={'p1':c.interfaces[0].id};w.library.save(d);w.refresh_library()
    try:
        w.place(d.id,0,0);w.place(d.id,300,0);a,b=w.project.instances.values()
        assert a.cavity_ref==b.cavity_ref==c.id
        w.remove_assignment(a.id);assert b.cavity_ref==c.id
        w.project.configure_ports(b.id,{'p1':'Supply'},{'p1':'TOP'})
        monkeypatch.setattr(QInputDialog,'getText',lambda *args,**kwargs:('Saved reusable',True))
        monkeypatch.setattr(QMessageBox,'question',lambda *args,**kwargs:QMessageBox.Yes)
        w.save_component_instance(b.id)
        saved=next(x for x in w.library.definitions.values() if x.name=='Saved reusable')
        assert saved.ports[0].display_name=='Supply' and saved.default_cavity_ref==c.id
        fresh=MainWindow(tmp_path/'components');fresh.place(saved.id,0,0)
        assert next(iter(fresh.project.instances.values())).cavity_ref==c.id;close_window(fresh)
    finally:close_window(w)


def test_alignment_port_priority_screen_tolerance_rotation_and_no_grid(qapp,tmp_path):
    w=MainWindow(tmp_path/'components');w.place('generic-2',0,0);w.place('generic-2',500,0)
    try:
        a,b=list(w.view.component_items.values());a.setSelected(True);b.setSelected(False)
        position=QPointF(113.125,77.375);assert w.view.aligned_position(a,position)==position
        for zoom in (1,2,.5):
            w.view.resetTransform();w.view.scale(zoom,zoom)
            proposed=QPointF(100,4/zoom);aligned=w.view.aligned_position(a,proposed)
            assert aligned.y()==pytest.approx(0) and aligned.x()==100 and w.view.alignment_guides
        w.project.rotate(b.instance.id);w.view.rebuild([a.instance.id]);a,b=list(w.view.component_items.values())
        target=next(iter(b.ports.values()));targetpoint=b.mapToScene(target.pos())
        source=next(iter(a.ports.values()));offset=a.mapToScene(source.pos())-a.pos()
        proposed=QPointF(123,targetpoint.y()-offset.y()+2)
        aligned=w.view.aligned_position(a,proposed);assert aligned.y()==pytest.approx(targetpoint.y()-offset.y())
        w.view.clear_alignment();assert not w.view.alignment_guides
        a.setPos(113.125,77.375);assert a.instance.x==113.125 and a.instance.y==77.375
    finally:close_window(w)


def test_long_labels_high_counts_layout_no_text_collisions(qapp,tmp_path):
    w=MainWindow(tmp_path/'components');d=generic_component(20);d.name='Long multiport engineering component'
    for i,p in enumerate(d.ports):p.display_name=f'Hydraulic connection label {i+1}';p.side=['LEFT','RIGHT','TOP','BOTTOM'][i%4]
    instance=w.project.add_instance(d);w.view.rebuild()
    try:
        item=w.view.component_items[instance.id];width,height=symbol_dimensions(d);assert width>110 and height>76
        title=__import__('PySide6.QtCore',fromlist=['QRectF']).QRectF(-len(d.name)*4,-14,len(d.name)*8,28)
        from PySide6.QtWidgets import QGraphicsSimpleTextItem
        texts=[child for child in item.childItems() if isinstance(child,QGraphicsSimpleTextItem) and child is not item.label]
        rects=[text.mapRectToParent(text.boundingRect()) for text in texts]
        assert all(not rect.intersects(title) for rect in rects)
        assert all(not a.intersects(b) for i,a in enumerate(rects) for b in rects[i+1:])
        assert all(item.boundingRect().contains(port.pos()) for port in item.ports.values())
    finally:close_window(w)


def test_actual_drag_guides_clear_on_release(qapp,tmp_path):
    from PySide6.QtTest import QTest
    from PySide6.QtCore import QPoint
    w=MainWindow(tmp_path/'components');w.show();w.place('generic-2',0,0);w.place('generic-2',500,120);w.view.fit_content();qapp.processEvents()
    try:
        a,b=list(w.view.component_items.values());start=w.view.mapFromScene(a.pos());end=w.view.mapFromScene(QPointF(50,118))
        QTest.mousePress(w.view.viewport(),Qt.LeftButton,pos=start);QTest.mouseMove(w.view.viewport(),end,delay=20);qapp.processEvents()
        assert w.view.alignment_guides and a.instance.y==pytest.approx(120,abs=.01)
        QTest.mouseRelease(w.view.viewport(),Qt.LeftButton,pos=end);qapp.processEvents();assert not w.view.alignment_guides
        w.project.validate()
    finally:close_window(w)


def test_revised_library_placement_preserves_existing_snapshot(qapp,tmp_path):
    w=MainWindow(tmp_path/'components');d=generic_component(2);w.library.save(d);w.refresh_library();w.place(d.id,0,0)
    original=next(iter(w.project.instances.values()));old_definition=deepcopy(w.project.definitions[original.definition_id])
    try:
        revised=deepcopy(w.library.definitions[d.id]);revised.ports[0].display_name='Updated default';w.library.update(revised);w.refresh_library();w.place(d.id,500,0)
        newest=list(w.project.instances.values())[-1]
        assert original.definition_id==d.id and w.project.definitions[d.id]==old_definition
        assert w.project.effective_definition(newest.id).ports[0].display_name=='Updated default'
        w.project.validate()
    finally:close_window(w)


def test_old_project_round_trip_preserves_all_geometry_identifiers(tmp_path):
    root=Path(__file__).resolve().parents[1]
    for path in (root/'examples').glob('*.amcad.json'):
        before=path.read_bytes();raw=json.loads(before);project=Project.load(path);project.save(tmp_path/path.name);reopened=Project.load(tmp_path/path.name)
        assert path.read_bytes()==before and reopened.to_dict()==project.to_dict()
        assert [(i['id'],i['definition_id']) for i in raw['component_instances']]==[(i.id,i.definition_id) for i in reopened.instances.values()]
        assert raw['nodes']==reopened.to_dict()['nodes']
        assert raw.get('cavity_definitions',[])==reopened.to_dict()['cavity_definitions']
        for original,loaded in zip(raw['component_definitions'],reopened.to_dict()['component_definitions']):
            if 'physical' in original:
                from core.component_definition import ComponentDefinition
                assert ComponentDefinition.from_dict(original).to_dict()['physical']==loaded['physical']
        for original,loaded in zip(raw['connections'],reopened.to_dict()['connections']):
            for key in original:
                if key!='schematic_geometry':assert original[key]==loaded[key]
            assert original['schematic_geometry']['controls']==loaded['schematic_geometry']['controls']
