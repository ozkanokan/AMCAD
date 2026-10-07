from copy import deepcopy
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QWidget,QLabel,QPushButton,
    QComboBox,QDoubleSpinBox,QDialogButtonBox,QTableWidget,QTableWidgetItem,QHeaderView,QCheckBox)
from core.cavity import CavityProfile,Corner,PhysicalDefinition,HydraulicInterface
from ui.cavity_sketch_view import CavitySketchView


def number(minimum=-1e6,maximum=1e6):
    widget=QDoubleSpinBox(); widget.setRange(minimum,maximum); widget.setDecimals(6); widget.setSingleStep(.1)
    return widget


class InterfaceDialog(QDialog):
    def __init__(self,ports,interfaces,marker=None,z=0,r=0,parent=None):
        super().__init__(parent); self.setWindowTitle('Hydraulic Interface Marker')
        self.marker=deepcopy(marker); self.result_marker=None
        form=QFormLayout(self)
        self.port=QComboBox()
        occupied={i.hydraulic_port_id for i in interfaces if marker is None or i.id!=marker.id}
        self.port.addItems([p.id for p in ports if p.id not in occupied])
        self.kind=QComboBox(); self.kind.addItems(['AXIAL','RADIAL'])
        self.z=number(); self.r=number(0); self.diameter=number(.000001)
        self.use_r=QCheckBox('Store R position'); self.use_r.setChecked(True)
        self.direction=QComboBox(); self.direction.addItems(['UNSPECIFIED','AXIAL_POSITIVE','AXIAL_NEGATIVE','RADIAL'])
        self.z.setValue(z); self.r.setValue(r); self.diameter.setValue(4)
        if marker:
            self.port.setCurrentText(marker.hydraulic_port_id); self.kind.setCurrentText(marker.interface_type)
            self.z.setValue(marker.z_mm); self.r.setValue(marker.r_mm or 0); self.use_r.setChecked(marker.r_mm is not None)
            self.diameter.setValue(marker.nominal_connection_diameter_mm); self.direction.setCurrentText(marker.preferred_direction)
        self.use_r.toggled.connect(self.r.setEnabled); self.r.setEnabled(self.use_r.isChecked())
        for label,widget in [('Schematic Port ID',self.port),('Interface Type',self.kind),('Z [mm]',self.z),
                             ('R [mm]',self.r),('',self.use_r),('Nominal Diameter [mm]',self.diameter),('Preferred Direction',self.direction)]: form.addRow(label,widget)
        self.feedback=QLabel(); form.addRow(self.feedback)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.submit); buttons.rejected.connect(self.reject); form.addRow(buttons)
        self.ports=ports

    def submit(self):
        marker=HydraulicInterface(self.port.currentText(),self.kind.currentText(),self.z.value(),
                                  self.r.value() if self.use_r.isChecked() else None,self.diameter.value(),self.direction.currentText())
        if self.marker: marker.id=self.marker.id
        try: marker.validate({p.id for p in self.ports})
        except ValueError as error: self.feedback.setText(str(error)); return
        self.result_marker=marker; self.accept()


class CavityEditor(QDialog):
    def __init__(self,ports,physical=None,parent=None):
        super().__init__(parent); self.setWindowTitle('Cavity Profile — Axisymmetric Sketcher V0.1'); self.resize(1120,760)
        self.ports=deepcopy(ports); self.physical=deepcopy(physical or PhysicalDefinition())
        self.profile=self.physical.cavity_profile or CavityProfile()
        self.interfaces=self.physical.hydraulic_interfaces
        self.result_physical=None; self.selected_id=None; self.updating=False
        root=QVBoxLayout(self); heading=QHBoxLayout()
        self.cavity_type=QComboBox(); self.cavity_type.addItems(['REVOLVED_PROFILE','NONE'])
        heading.addWidget(QLabel('Cavity Type')); heading.addWidget(self.cavity_type)
        heading.addWidget(QLabel('mm • Z=0 mounting face • positive Z into manifold • R=0 fixed axis')); heading.addStretch()
        root.addLayout(heading)
        body=QHBoxLayout(); self.view=CavitySketchView(self.profile,self.interfaces); body.addWidget(self.view,1)
        properties=QWidget(); form=QFormLayout(properties); properties.setMaximumWidth(350)
        self.point_id=QLabel('Select a profile point'); self.point_id.setWordWrap(True)
        self.z=number(); self.r=number(0); self.z.setEnabled(False); self.r.setEnabled(False)
        self.corner=QComboBox(); self.corner.addItems(['SHARP','FILLET','CHAMFER'])
        self.radius=number(.000001); self.radius.setValue(.5)
        self.length=number(.000001); self.length.setValue(.5)
        self.angle=number(.000001,179.999999); self.angle.setValue(45)
        for label,widget in [('Point ID',self.point_id),('Z [mm]',self.z),('R [mm]',self.r),('Corner',self.corner),
                             ('Radius [mm]',self.radius),('Chamfer Length [mm]',self.length),('Angle [deg]',self.angle)]: form.addRow(label,widget)
        apply=QPushButton('Apply Corner'); apply.clicked.connect(self.apply_corner); form.addRow(apply)
        form.addRow(QLabel('Hydraulic Interface Markers'))
        self.markers=QTableWidget(0,2); self.markers.setHorizontalHeaderLabels(['Port ID','Type / Z [mm]'])
        self.markers.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.markers.setMaximumHeight(180)
        self.markers.setEditTriggers(QTableWidget.NoEditTriggers); form.addRow(self.markers)
        add_marker=QPushButton('Place Interface Marker'); add_marker.clicked.connect(self.begin_marker); form.addRow(add_marker)
        edit_marker=QPushButton('Edit Selected Interface'); edit_marker.clicked.connect(self.edit_marker); form.addRow(edit_marker)
        remove_marker=QPushButton('Remove Selected Interface'); remove_marker.clicked.connect(self.remove_marker); form.addRow(remove_marker)
        body.addWidget(properties); root.addLayout(body,1)
        toolbar=QHBoxLayout()
        self.add_button=QPushButton('Add Point'); self.add_button.setCheckable(True); self.add_button.setChecked(True)
        self.add_button.toggled.connect(lambda enabled:setattr(self.view,'add_mode',enabled)); toolbar.addWidget(self.add_button)
        for label,callback in [('Insert After Selected',self.insert_point),('Delete Point',self.delete_point),
                               ('Sharp',lambda:self.choose_corner('SHARP')),('Fillet',lambda:self.choose_corner('FILLET')),
                               ('Chamfer',lambda:self.choose_corner('CHAMFER')),('Fit',self.view.fit_profile)]:
            button=QPushButton(label); button.clicked.connect(callback); toolbar.addWidget(button)
        self.preview=QPushButton('Revolve Preview'); self.preview.setCheckable(True); self.preview.toggled.connect(self.set_preview); toolbar.addWidget(self.preview)
        self.snap=QComboBox(); self.snap.addItems(['Snap OFF','0.1 mm','0.5 mm','1.0 mm']); self.snap.setCurrentIndex(2)
        self.snap.currentIndexChanged.connect(lambda index:setattr(self.view,'snap_increment',[0,.1,.5,1][index]))
        toolbar.addWidget(self.snap); root.addLayout(toolbar)
        self.validity=QLabel(); self.warnings=QLabel(); self.warnings.setWordWrap(True); self.feedback=QLabel(); self.feedback.setWordWrap(True)
        root.addWidget(self.validity); root.addWidget(self.warnings); root.addWidget(self.feedback)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.submit); buttons.rejected.connect(self.reject); root.addWidget(buttons)
        self.view.point_selected.connect(self.select_point); self.view.profile_changed.connect(self.profile_changed)
        self.view.message.connect(self.feedback.setText); self.view.marker_requested.connect(self.place_marker)
        self.z.valueChanged.connect(self.numeric_edit); self.r.valueChanged.connect(self.numeric_edit)
        self.cavity_type.currentTextChanged.connect(self.type_changed)
        self.refresh_markers(); self.profile_changed(); self.view.fit_profile()

    def showEvent(self,event):
        super().showEvent(event)
        self.view.fit_profile()

    def type_changed(self):
        self.view.setEnabled(self.cavity_type.currentText()!='NONE'); self.profile_changed()

    def select_point(self,vertex_id):
        self.selected_id=vertex_id or None; self.updating=True
        self.z.setEnabled(bool(vertex_id)); self.r.setEnabled(bool(vertex_id))
        if vertex_id:
            v=self.profile.vertex(vertex_id); self.point_id.setText(v.id)
            self.z.setValue(v.z); self.r.setValue(v.r); self.corner.setCurrentText(v.corner.type)
            if v.corner.radius_mm is not None: self.radius.setValue(v.corner.radius_mm)
            if v.corner.length_mm is not None: self.length.setValue(v.corner.length_mm)
            if v.corner.angle_deg is not None: self.angle.setValue(v.corner.angle_deg)
        else: self.point_id.setText('Select a profile point')
        self.updating=False

    def numeric_edit(self):
        if self.updating or not self.selected_id: return
        selected=self.selected_id
        try: self.profile.edit_point(selected,self.z.value(),self.r.value())
        except ValueError as error:
            self.feedback.setText(str(error)); self.select_point(selected); return
        self.view.rebuild(selected); self.profile_changed()

    def profile_changed(self):
        errors=[] if self.cavity_type.currentText()=='NONE' else self.profile.validation_errors()
        self.validity.setText('INVALID: '+errors[0] if errors else 'VALID')
        self.validity.setStyleSheet('color: #b3261e' if errors else 'color: #267343')
        physical=PhysicalDefinition(self.cavity_type.currentText(),self.profile,self.interfaces)
        self.warnings.setText('; '.join(physical.warnings(self.ports)))
        if self.selected_id: self.select_point(self.selected_id)

    def choose_corner(self,kind):
        self.corner.setCurrentText(kind); self.apply_corner()

    def apply_corner(self):
        if not self.selected_id: self.feedback.setText('Select an internal profile point'); return
        kind=self.corner.currentText()
        corner=Corner(kind,radius_mm=self.radius.value()) if kind=='FILLET' else Corner(kind,length_mm=self.length.value(),angle_deg=self.angle.value()) if kind=='CHAMFER' else Corner()
        try: self.profile.set_corner(self.selected_id,corner)
        except ValueError as error: self.feedback.setText(str(error)); return
        self.feedback.clear(); self.view.refresh_path(); self.profile_changed()

    def insert_point(self):
        if not self.selected_id: self.feedback.setText('Select the point preceding the insertion'); return
        self.view.insert_after=self.selected_id; self.add_button.setChecked(True)
        self.feedback.setText('Click the canvas to insert after the selected point')

    def delete_point(self):
        if not self.selected_id: return
        try: self.profile.delete_point(self.selected_id)
        except ValueError as error: self.feedback.setText(str(error)); return
        self.selected_id=None; self.view.rebuild(); self.select_point(''); self.profile_changed()

    def set_preview(self,enabled):
        self.view.mirrored=enabled; self.view.refresh_path(); self.view.fit_profile()
        self.feedback.setText('Mirrored cross-section preview; no 3D solid or CAD kernel' if enabled else '')

    def refresh_markers(self):
        self.markers.setRowCount(len(self.interfaces))
        for row,marker in enumerate(self.interfaces):
            self.markers.setItem(row,0,QTableWidgetItem(marker.hydraulic_port_id))
            self.markers.setItem(row,1,QTableWidgetItem(f'{marker.interface_type} / {marker.z_mm:g}'))

    def begin_marker(self):
        if len(self.interfaces)>=len(self.ports): self.feedback.setText('All schematic ports already have an interface'); return
        self.view.marker_mode=True; self.feedback.setText('Click the sketch to place a hydraulic interface marker')

    def place_marker(self,z,r):
        dialog=InterfaceDialog(self.ports,self.interfaces,z=z,r=r,parent=self)
        if dialog.exec()==QDialog.Accepted:
            self.interfaces.append(dialog.result_marker); self.refresh_markers(); self.view.rebuild(self.selected_id); self.profile_changed()

    def edit_marker(self):
        row=self.markers.currentRow()
        if row<0: return
        dialog=InterfaceDialog(self.ports,self.interfaces,self.interfaces[row],parent=self)
        if dialog.exec()==QDialog.Accepted:
            self.interfaces[row]=dialog.result_marker; self.refresh_markers(); self.view.rebuild(self.selected_id); self.profile_changed()

    def remove_marker(self):
        row=self.markers.currentRow()
        if row<0: return
        del self.interfaces[row]; self.refresh_markers(); self.view.rebuild(self.selected_id); self.profile_changed()

    def submit(self):
        physical=PhysicalDefinition() if self.cavity_type.currentText()=='NONE' else PhysicalDefinition('REVOLVED_PROFILE',self.profile,self.interfaces)
        try: physical.validate(self.ports)
        except ValueError as error: self.feedback.setText(str(error)); return
        self.result_physical=deepcopy(physical); self.accept()
