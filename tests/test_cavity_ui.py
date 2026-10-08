from copy import deepcopy
import json
from pathlib import Path
import pytest
from PySide6.QtCore import Qt,QPointF,QPoint,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog,QTableWidgetItem,QPushButton
from core.cavity import CavityProfile,PhysicalDefinition,Corner
from core.component_definition import ComponentDefinition
from core.project import Project
from core.history import ProjectHistory
from core.graph import export_graph
from core.library import ComponentLibrary
from core.port import PortDefinition
from examples.create_physical_demo import check_valve_definition
from ui.cavity_editor import CavityEditor,InterfaceDialog
from ui.cavity_sketch_view import profile_path
from ui.node_wizard import NodeWizard
from ui.main_window import MainWindow

ROOT=Path(__file__).resolve().parents[1]


def click_point(editor,z,r):
    QTest.mouseClick(editor.view.viewport(),Qt.LeftButton,pos=editor.view.mapFromScene(QPointF(z,-r)))


def test_visual_creation_drag_snap_numeric_insert_delete(qapp):
    ports=[PortDefinition('IN','IN'),PortDefinition('OUT','OUT')]
    editor=CavityEditor(ports); editor.show(); editor.correct_endpoints(); qapp.processEvents()
    assert editor.validity.text().startswith('INVALID')
    editor.view.resetTransform(); editor.view.scale(25,25); editor.view.centerOn(10,-5)
    editor.points.item(1,1).setText("30")
    for z,r in [(0.31,4.74),(10,5),(10,8),(25,8)]:
        click_point(editor,z,r); qapp.processEvents()
    assert len(editor.profile.vertices)==6
    first=editor.profile.vertices[1]
    assert (first.z,first.r)==(.5,4.5)
    assert editor.validity.text()=='VALID'
    editor.view.scene().clearSelection(); editor.view.point_items[first.id].setSelected(True)
    editor.points.item(1,1).setText('.123456'); editor.points.item(1,2).setText('4.654321'); qapp.processEvents()
    assert (first.z,first.r)==(.123456,4.654321)  # Numeric input bypasses grid snap.
    start=editor.view.mapFromScene(QPointF(first.z,-first.r)); end=start+QPoint(19,-13)
    editor.set_mode(False)
    QTest.mousePress(editor.view.viewport(),Qt.LeftButton,pos=start)
    QTest.mouseMove(editor.view.viewport(),end,delay=20)
    QTest.mouseRelease(editor.view.viewport(),Qt.LeftButton,pos=end); qapp.processEvents()
    assert first.z%.5==pytest.approx(0) and first.r%.5==pytest.approx(0)
    assert first.id==editor.selected_id
    editor.insert_point(); click_point(editor,5,5.5); qapp.processEvents()
    inserted=editor.profile.vertices[2]
    assert (inserted.z,inserted.r)==(5,5.5) and len(editor.profile.vertices)==7
    editor.delete_point(); assert len(editor.profile.vertices)==6
    # Dragging below the fixed axis clamps to R=0, never a negative radius.
    editor.view.point_items[first.id].setPos(first.z,10)
    assert first.r==0
    editor.reject()


def test_corner_controls_exact_profile_mirror_and_invalid_rollback(qapp):
    definition=check_valve_definition(); editor=CavityEditor(definition.ports,definition.physical)
    editor.show(); editor.correct_endpoints(); qapp.processEvents()
    vertex=editor.profile.vertices[1]; editor.view.point_items[vertex.id].setSelected(True)
    editor.points.item(1,3).setText('.75')
    assert vertex.corner.radius_mm==.75 and len(editor.profile.vertices)==6
    path=profile_path(editor.profile)
    assert any(path.elementAt(i).isCurveTo() for i in range(path.elementCount()))
    before=editor.profile.to_dict(); editor.points.item(1,3).setText('500')
    assert editor.profile.to_dict()==before and 'too large' in editor.feedback.text()
    editor.points.item(1,3).setText('0'); assert vertex.corner.type=='SHARP'
    editor.points.item(1,4).setText('.5')
    assert vertex.corner.length_mm==.5 and vertex.corner.angle_deg==45
    before=editor.profile.to_dict(); editor.preview.setChecked(True)
    assert not editor.view.mirror_item.path().isEmpty() and editor.profile.to_dict()==before
    editor.grab().save('/tmp/amcad-cavity-v13.png')
    editor.submit(); assert editor.result()==QDialog.Accepted
    assert editor.result_physical.cavity_type=='REVOLVED_PROFILE'
    # Caller definition was never modified while editing the dialog copy.
    assert definition.physical.cavity_profile.vertices[1].corner.radius_mm==.5


def test_interface_marker_placement_edit_and_duplicate_block(qapp):
    definition=check_valve_definition(); physical=deepcopy(definition.physical); physical.hydraulic_interfaces=[]
    editor=CavityEditor(definition.ports,physical); editor.show(); editor.correct_endpoints(); qapp.processEvents()
    assert 'IN' in editor.warnings.text() and 'OUT' in editor.warnings.text()
    def accept_interface():
        dialog=editor.findChild(InterfaceDialog)
        dialog.port.setCurrentText('OUT'); dialog.submit()
    QTimer.singleShot(0,accept_interface)
    editor.begin_marker(); click_point(editor,14.5,5); qapp.processEvents()
    assert len(editor.interfaces)==1 and editor.interfaces[0].hydraulic_port_id=='OUT'
    assert editor.interfaces[0].z_mm==14.5 and editor.interfaces[0].interface_type=='SURFACE'
    duplicate=InterfaceDialog(definition.ports,editor.interfaces,profile=editor.profile,anchor=editor.interfaces[0].surface_anchor)
    assert [duplicate.port.itemText(i) for i in range(duplicate.port.count())]==['IN']
    duplicate.port.setCurrentText('IN'); duplicate.submit()
    editor.interfaces.append(duplicate.result_marker); editor.refresh_markers(); editor.profile_changed()
    assert not editor.warnings.text()
    marker_id=editor.interfaces[0].id; editor.markers.selectRow(0)
    def edit_interface():
        dialogs=editor.findChildren(InterfaceDialog)
        dialog=dialogs[-1]; dialog.parameter.setValue(.59375); dialog.submit()
    QTimer.singleShot(0,edit_interface); editor.edit_marker()
    assert editor.interfaces[0].id==marker_id and editor.interfaces[0].surface_anchor.t==.594
    editor.submit(); editor.result_physical.validate(definition.ports)


def test_wizard_integrates_cavity_and_library_reopen(qapp,tmp_path):
    wizard=NodeWizard(); wizard.name.setText('Custom Check Valve'); wizard.prefix.setText('CV')
    for row,port_id in enumerate(['IN','OUT']):
        wizard.ports.setItem(row,0,QTableWidgetItem(port_id)); wizard.ports.setItem(row,1,QTableWidgetItem(port_id))
    wizard.add_relationship()
    for col,text in enumerate(['IN','OUT','CHECK_VALVE']): wizard.relationships.setItem(0,col,QTableWidgetItem(text))
    def fill_editor():
        editor=wizard.findChild(CavityEditor)
        sample=check_valve_definition().physical
        editor.profile.vertices=deepcopy(sample.cavity_profile.vertices)
        editor.interfaces.extend(deepcopy(sample.hydraulic_interfaces))
        editor.correct_endpoints(); editor.view.rebuild(); editor.profile_changed(); editor.submit()
    QTimer.singleShot(0,fill_editor); wizard.edit_cavity(); wizard.submit()
    assert wizard.result()==QDialog.Accepted and wizard.definition.physical.cavity_type=='REVOLVED_PROFILE'
    library=ComponentLibrary(tmp_path/'library'); library.save(wizard.definition)
    loaded=ComponentLibrary(tmp_path/'library').definitions[wizard.definition.id]
    assert loaded.to_dict()==wizard.definition.to_dict()
    reopen=CavityEditor(loaded.ports,loaded.physical); reopen.show(); qapp.processEvents()
    assert reopen.validity.text()=='VALID'
    assert reopen.profile.to_dict()==loaded.physical.cavity_profile.to_dict()
    assert len(reopen.interfaces)==2; reopen.reject()


def test_shared_definition_edit_undo_and_old_clipboard(qapp,tmp_path):
    definition=check_valve_definition()
    w=MainWindow(tmp_path/'library'); w.library.save(definition); w.refresh_library()
    w.place(definition.id,-100,0); w.place(definition.id,100,0)
    instance_ids=list(w.project.instances); original=deepcopy(w.project.definitions[definition.id].physical)
    clipboard=w.project.copy_subgraph(instance_ids)
    def edit_cavity():
        editor=w.findChild(CavityEditor)
        editor.correct_endpoints()
        editor.view.point_items[editor.profile.vertices[-1].id].setSelected(True)
        editor.points.item(len(editor.profile.vertices)-1,1).setText('29.125'); editor.submit()
    QTimer.singleShot(0,edit_cavity); w.edit_definition_cavity(definition.id)
    assert w.project.definitions[definition.id].physical.cavity_profile.vertices[-1].z==29.125
    assert all(w.project.instances[i].definition_id==definition.id for i in instance_ids)
    assert ComponentLibrary(tmp_path/'library').definitions[definition.id].physical.cavity_profile.vertices[-1].z==29.125
    w.undo(); assert w.project.definitions[definition.id].physical==original
    w.redo(); updated=deepcopy(w.project.definitions[definition.id].physical)
    added=w.project.paste_subgraph(clipboard)
    assert all(w.project.instances[i].definition_id==definition.id for i in added)
    assert len(w.project.definitions)==1 and w.project.definitions[definition.id].physical==updated
    w.save_to(tmp_path/'shared.json'); expected=w.project.to_dict(); w.close()
    reopened=MainWindow(tmp_path/'library'); reopened.load_path(tmp_path/'shared.json')
    assert reopened.project.to_dict()==expected
    reopened.close()


def test_physical_demo_launch_graph_and_existing_c1_r_preserved(qapp,tmp_path):
    demo=ROOT/'examples/parallel_check_valves.amcad.json'
    p=Project.load(demo)
    assert len(p.instances)==6 and len(p.nodes)==10 and len(p.connections)==5
    cvs=[i for i in p.instances.values() if i.name in ('CV1','CV2')]
    assert len(cvs)==2 and cvs[0].definition_id==cvs[1].definition_id
    definition=p.definitions[cvs[0].definition_id]
    assert definition.physical.cavity_type=='REVOLVED_PROFILE'
    assert {i.hydraulic_port_id for i in definition.physical.hydraulic_interfaces}=={'IN','OUT'}
    assert all(p.is_complete(i.id) for i in p.instances.values())
    assert p.to_dict()['schema_version']==5
    assert export_graph(p)==json.loads((ROOT/'examples/parallel_check_valves.graph.json').read_text())
    assert sum(d['physical']['cavity_type']=='REVOLVED_PROFILE' for d in export_graph(p)['component_definitions'])==1
    w=MainWindow(tmp_path/'library'); w.load_path(demo); w.show(); qapp.processEvents()
    w.grab().save('/tmp/amcad-physical-demo-v13.png'); w.close()
    original=Project.load(ROOT/'examples/c1_r.amcad.json')
    assert len(original.connections)==6 and all(d.physical.cavity_type=='NONE' for d in original.definitions.values())
    original.save(tmp_path/'c1.json')
    assert Project.load(tmp_path/'c1.json').to_dict()==original.to_dict()
