import json
from PySide6.QtCore import Qt, QPoint, QPointF, QMimeData, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QTableWidgetItem, QDialog, QLineEdit, QDialogButtonBox
from ui.main_window import MainWindow
from ui.node_wizard import NodeWizard
from ui.component_library import MIME_TYPE
from core.library import ComponentLibrary
from core.history import ProjectHistory
from core.project import Project


def wizard_component(qapp, name, prefix, ports, relationships=()):
    wizard=NodeWizard()
    wizard.show(); qapp.processEvents()
    QTest.keyClicks(wizard.name,name)
    QTest.keyClicks(wizard.prefix,prefix)
    wizard.count.setValue(len(ports))
    for row, (port_id,side,flow) in enumerate(ports):
        wizard.ports.setItem(row,0,QTableWidgetItem(port_id))
        wizard.ports.setItem(row,1,QTableWidgetItem(port_id))
        wizard.ports.cellWidget(row,3).setCurrentText(flow)
        wizard.ports.cellWidget(row,4).setCurrentText(side)
    for source,target,kind in relationships:
        wizard.add_relationship()
        row=wizard.relationships.rowCount()-1
        for col,text in enumerate([source,target,kind]):
            wizard.relationships.setItem(row,col,QTableWidgetItem(text))
    wizard.submit()
    assert wizard.result()==QDialog.Accepted
    assert wizard.preview.scene().items()
    return wizard.definition


def click_port(window,node_id,qapp):
    pos=window.view.mapFromScene(window.view.port_items[node_id].scenePos())
    QTest.mouseClick(window.view.viewport(),Qt.LeftButton,pos=pos)
    qapp.processEvents()


def test_full_desktop_acceptance(qapp,tmp_path):
    window=MainWindow(tmp_path/'library'); window.show(); qapp.processEvents()
    ehsv=wizard_component(qapp,'EHSV','EHSV',[
        ('P','TOP','IN'),('R','BOTTOM','OUT'),('C1','LEFT','BIDIRECTIONAL'),('C2','RIGHT','BIDIRECTIONAL')])
    rv=wizard_component(qapp,'Relief Valve','RV',[
        ('IN','LEFT','IN'),('OUT','RIGHT','OUT')],[('IN','OUT','RELIEF_VALVE')])
    window.library.save(ehsv); window.library.save(rv); window.refresh_library()
    assert ehsv.id in ComponentLibrary(tmp_path/'library').definitions
    for definition,x,y in [('external-port',-300,-60),('external-port',320,170),
                            (ehsv.id,20,-100),(rv.id,20,170),('junction',-150,-60)]:
        window.place(definition,x,y)
    c1,ret,e,r,j=list(window.project.instances.values())
    window.project.rename(c1.id,'C1'); window.project.rename(ret.id,'R')
    window.view.rebuild(); window.record_change(); window.view.fit_content(); qapp.processEvents()
    for a,ap,b,bp in [(c1,'port',j,'j'),(j,'j',e,'C1'),(j,'j',r,'IN'),(r,'OUT',ret,'port'),(e,'R',ret,'port')]:
        click_port(window,window.project.node_for(a.id,ap).id,qapp)
        click_port(window,window.project.node_for(b.id,bp).id,qapp)
    assert len(window.project.connections)==5
    edges=[(c.from_node_id,c.to_node_id) for c in window.project.connections.values()]
    rv_item=window.view.component_items[r.id]
    original_endpoint=window.view.port_items[window.project.node_for(r.id,'IN').id].scenePos()
    rv_item.setSelected(True)
    window.activateWindow(); window.view.setFocus(); qapp.processEvents()
    origin=window.view.mapFromScene(rv_item.scenePos())
    destination=origin+QPoint(40,30)
    QTest.mousePress(window.view.viewport(),Qt.LeftButton,pos=origin)
    QTest.mouseMove(window.view.viewport(),destination,delay=20)
    QTest.mouseRelease(window.view.viewport(),Qt.LeftButton,pos=destination)
    qapp.processEvents()
    assert window.view.port_items[window.project.node_for(r.id,'IN').id].scenePos()!=original_endpoint
    window.activateWindow(); window.view.setFocus(); qapp.processEvents()
    QTest.keyClick(window.view,Qt.Key_R,Qt.ControlModifier); qapp.processEvents()
    assert r.rotation==90
    for wire in window.view.wires.values():
        start=wire.path().elementAt(0)
        end=wire.path().elementAt(wire.path().elementCount()-1)
        a=window.view.port_items[wire.connection.from_node_id].scenePos()
        b=window.view.port_items[wire.connection.to_node_id].scenePos()
        assert (start.x,start.y)==(a.x(),a.y()) and (end.x,end.y)==(b.x(),b.y())
    assert [(c.from_node_id,c.to_node_id) for c in window.project.connections.values()]==edges
    window.save_to(tmp_path/'project.json')
    expected=window.project.to_dict()
    window.close(); qapp.processEvents()
    reopened=MainWindow(tmp_path/'library'); reopened.load_path(tmp_path/'project.json')
    reopened.show(); qapp.processEvents()
    assert reopened.project.to_dict()==expected
    assert len(reopened.view.component_items)==5 and len(reopened.view.wires)==5
    reopened.export_to(tmp_path/'graph.json')
    graph=json.loads((tmp_path/'graph.json').read_text())
    assert len(graph['nodes'])==9 and len(graph['junctions'])==1
    assert len(graph['routing_connections'])==5
    assert len(graph['component_internal_relationships'])==1
    assert {n['label'] for n in graph['nodes']} >= {'C1','R','EHSV1.C1','RV1.IN'}
    reopened.grab().save('/tmp/amcad-acceptance.png')
    reopened.close()


def test_editing_controls_and_drop(qapp,tmp_path):
    w=MainWindow(tmp_path/'library'); w.show(); qapp.processEvents()
    mime=QMimeData(); mime.setData(MIME_TYPE,b'generic-2')
    center=w.view.viewport().rect().center()
    enter=QDragEnterEvent(center,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
    qapp.sendEvent(w.view.viewport(),enter)
    assert enter.isAccepted()
    drop=QDropEvent(QPointF(center),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
    qapp.sendEvent(w.view.viewport(),drop)
    assert drop.isAccepted() and len(w.project.instances)==1
    first=next(iter(w.project.instances.values()))
    w.view.component_items[first.id].setSelected(True)
    w.copy(); w.paste()
    assert len(w.project.instances)==2 and len(w.project.nodes)==4
    w.undo(); assert len(w.project.instances)==1
    w.redo(); assert len(w.project.instances)==2
    w.select_all(); assert len(w.view.selected_instances())==2
    QTest.keyClick(w.view,Qt.Key_Delete); qapp.processEvents()
    assert not w.project.instances and not w.project.nodes
    w.undo(); assert len(w.project.instances)==2
    w.view.rebuild()
    ids=list(w.project.nodes)
    click_port(w,ids[0],qapp); QTest.keyClick(w.view,Qt.Key_Escape)
    assert w.view.pending_node is None
    click_port(w,ids[0],qapp); click_port(w,ids[2],qapp)
    assert len(w.project.connections)==1
    edge=next(iter(w.view.wires.values())); edge.setSelected(True)
    w.delete_selection(); assert not w.project.connections
    w.undo(); assert len(w.project.connections)==1
    scale=w.view.transform().m11(); w.view.zoom(1.15)
    assert w.view.transform().m11()>scale
    before=w.view.horizontalScrollBar().value()
    QTest.mousePress(w.view.viewport(),Qt.MiddleButton,pos=center)
    QTest.mouseMove(w.view.viewport(),center+QPoint(50,0))
    QTest.mouseRelease(w.view.viewport(),Qt.MiddleButton,pos=center+QPoint(50,0))
    assert w.view.horizontalScrollBar().value()!=before
    # Exercise the actual modal properties dialog and persistent rename.
    selected_id=next(iter(w.project.instances))
    def rename_dialog():
        dialog=w.findChild(QDialog)
        dialog.findChild(QLineEdit).setText('Renamed')
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
    QTimer.singleShot(0,rename_dialog)
    w.properties(selected_id)
    assert w.project.instances[selected_id].name=='Renamed'
    w.save_to(tmp_path/'edited.json'); w.close()


def test_wizard_validation_and_history(qapp):
    wizard=NodeWizard(); wizard.name.setText('Valve'); wizard.prefix.setText('V')
    wizard.ports.item(1,0).setText(wizard.ports.item(0,0).text())
    wizard.submit()
    assert wizard.result()!=QDialog.Accepted and wizard.error_label.text()
    wizard.reject()
    p=Project(); history=ProjectHistory(p)
    definition=ComponentLibrary('/tmp/amcad-test-no-library').definitions['generic-2']
    i=p.add_instance(definition); history.record(p)
    p.rename(i.id,'Valve'); history.record(p)
    assert history.undo().instances[i.id].name!='Valve'
    assert history.redo().instances[i.id].name=='Valve'
