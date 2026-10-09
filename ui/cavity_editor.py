from copy import deepcopy
import math
from PySide6.QtCore import Qt, QLocale, QTimer
from PySide6.QtGui import QDoubleValidator, QColor, QPalette
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QWidget,
    QLabel, QPushButton, QComboBox, QDoubleSpinBox, QDialogButtonBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QStyledItemDelegate, QLineEdit, QGroupBox, QSplitter, QToolButton, QSizePolicy)
from core.port import PortDefinition,new_id
from core.cavity_definition import CavityDefinition
from core.cavity import CavityProfile, ProfileVertex, Corner, PhysicalDefinition, HydraulicInterface
from ui.cavity_sketch_view import CavitySketchView
from core.cavity_surface import (SurfaceAnchor, ChannelSection, normalized, surface_patches,
    resolve_anchor, interface_pose, revolved_surface, anchor_key, legacy_surface_anchor)
from ui.cavity_surface_view import CavitySurfaceView


def number(minimum=-1e6, maximum=1e6):
    widget = QDoubleSpinBox()
    widget.setLocale(QLocale.c())
    widget.setGroupSeparatorShown(False)
    widget.setRange(minimum, maximum)
    widget.setDecimals(12)
    widget.setSingleStep(.1)
    return widget


def numeric_text(value):
    """Shortest round-trippable decimal text; presentation never rounds stored values."""
    return str(int(value)) if value == int(value) else str(value)


class PointNumberDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setLocale(QLocale.c())
        validator = QDoubleValidator(editor)
        locale = QLocale.c()
        locale.setNumberOptions(QLocale.RejectGroupSeparator)
        validator.setLocale(locale)
        validator.setNotation(QDoubleValidator.ScientificNotation)
        editor.setValidator(validator)
        return editor


class CollapsiblePanel(QWidget):
    def __init__(self,title,parent=None):
        super().__init__(parent)
        layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        self.header=QToolButton(); self.header.setText(title); self.header.setCheckable(True)
        self.header.setChecked(True); self.header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.header.setArrowType(Qt.DownArrow)
        self.header.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        self.contents=QWidget(); self.content_layout=QVBoxLayout(self.contents)
        self.content_layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self.header); layout.addWidget(self.contents,1)
        self.header.toggled.connect(self.set_expanded)

    def set_expanded(self,expanded):
        self.header.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.contents.setVisible(expanded)
        self.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Expanding if expanded else QSizePolicy.Maximum)


def interface_number(value=0,minimum=-1e6,maximum=1e6,step=.1):
    widget=number(minimum,maximum); widget.setDecimals(3); widget.setSingleStep(step); widget.setValue(value)
    return widget


def feature_label(index,patch):
    start,_=patch.evaluate(0); end,_=patch.evaluate(1)
    radius=f" | R_fillet {patch.feature['radius']:.3f} mm" if patch.anchor.kind=='FILLET' else ''
    return f"{index+1} — {patch.anchor.kind} | Z {start[0]:.3f} → {end[0]:.3f} mm | Y {start[1]:.3f} → {end[1]:.3f} mm"+radius


class InterfaceDialog(QDialog):
    def __init__(self,ports,interfaces,marker=None,z=0,r=0,parent=None,profile=None,anchor=None):
        super().__init__(parent); self.setLocale(QLocale.c()); self.setWindowTitle('Hydraulic Interface')
        self.ports=ports; self.marker=deepcopy(marker); self.profile=profile; self.result_marker=None
        self.anchor=deepcopy(anchor or (marker.surface_anchor if marker else None))
        if self.anchor is None and marker and profile:
            self.anchor=legacy_surface_anchor(profile,marker)
        root=QVBoxLayout(self)
        def group(title):
            box=QGroupBox(title); form=QFormLayout(box); root.addWidget(box); return form
        independent=bool(getattr(parent,'independent',False))
        form=group('1. Hydraulic Interface' if independent else '1. Schematic Port'); self.port=QComboBox()
        occupied={i.hydraulic_port_id for i in interfaces if marker is None or i.id!=marker.id}
        for p in ports:
            if p.id not in occupied:self.port.addItem(p.display_name if independent else p.id,p.id)
        if marker:self.port.setCurrentIndex(self.port.findData(marker.hydraulic_port_id))
        form.addRow('Independent interface' if independent else 'Component port ID',self.port)
        form=group('2. Surface Anchor'); self.feature=QComboBox()
        self.feature.addItem('Unresolved legacy position — choose a surface explicitly',None)
        try: patches=surface_patches(profile) if profile else []
        except ValueError: patches=[]
        for index,patch in enumerate(patches): self.feature.addItem(feature_label(index,patch),patch.anchor)
        if self.anchor:
            match=next((i for i in range(1,self.feature.count()) if anchor_key(self.feature.itemData(i))==anchor_key(self.anchor)),None)
            if match is None:
                self.feature.addItem('INVALID original anchor — choose a new surface explicitly',self.anchor); match=self.feature.count()-1
            self.feature.setCurrentIndex(match)
        self.parameter=interface_number(self.anchor.t if self.anchor else .5,0,1,.01)
        self.azimuth=interface_number(self.anchor.angle_deg if self.anchor else 0,-360000,360000,1)
        self.initial_anchor=deepcopy(self.anchor); self.initial_anchor_controls=(self.parameter.value(),self.azimuth.value())
        form.addRow('Surface feature',self.feature); row=QHBoxLayout()
        row.addWidget(QLabel('Along [0–1]')); row.addWidget(self.parameter); row.addWidget(QLabel('Angle (°)')); row.addWidget(self.azimuth)
        form.addRow(row); self.xyz_label=QLabel(); form.addRow('Resolved XYZ (mm)',self.xyz_label)
        try: vector=interface_pose(profile,marker)[1] if marker else resolve_anchor(profile,self.anchor)[1] if self.anchor else (0,0,1)
        except ValueError: vector=marker.direction or (0,0,1)
        form=group('3. Channel Direction'); self.vector=[interface_number(v,step=.01) for v in vector]
        row=QHBoxLayout()
        for label,widget in zip(('dx','dy','dz'),self.vector): row.addWidget(QLabel(label)); row.addWidget(widget)
        form.addRow(row); form.addRow(QLabel('Nonzero channel axis; normalized without changing its sign.'))
        form=group('4. Cross Section'); self.section_type=QComboBox(); self.section_type.addItems(['CIRCLE','SLOT','RECTANGLE'])
        section=marker.section if marker and marker.section else ChannelSection(diameter_mm=marker.nominal_connection_diameter_mm if marker else 4)
        self.section_type.setCurrentText(section.type)
        self.circle_diameter=interface_number(section.diameter_mm,.001); self.width=interface_number(section.width_mm,.001)
        self.length=interface_number(section.length_mm,.001); self.height=interface_number(section.height_mm,.001)
        self.rotation=interface_number(marker.section_rotation_deg if marker else 0,-360000,360000,1)
        form.addRow('Section',self.section_type); row=QHBoxLayout()
        for label,widget in [('Diameter',self.circle_diameter),('Width',self.width),('Overall length',self.length),('Height',self.height)]:
            row.addWidget(QLabel(label)); row.addWidget(widget)
        form.addRow('Sizes (mm)',row); form.addRow('Section rotation (°)',self.rotation)
        form=group('5. Preview')
        self.preview_length=interface_number(marker.preview_length_mm if marker else 2,.001)
        form.addRow('Total extent (mm)',self.preview_length)
        form.addRow(QLabel('Centered ±half extent for new ports; legacy forward extents stay unchanged.'))
        self.original_vector=tuple(w.value() for w in self.vector)
        self.original_section=(self.section_type.currentText(),self.circle_diameter.value(),self.width.value(),self.length.value(),self.height.value())
        self.original_preview=(self.rotation.value(),self.preview_length.value())
        self.feedback=QLabel(); self.feedback.setWordWrap(True); root.addWidget(self.feedback)
        self.buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.submit); self.buttons.rejected.connect(self.reject); root.addWidget(self.buttons)
        self.feature.currentIndexChanged.connect(self.update_anchor); self.parameter.valueChanged.connect(self.update_anchor); self.azimuth.valueChanged.connect(self.update_anchor)
        self.section_type.currentTextChanged.connect(self.section_changed)
        self.section_changed(); self.update_anchor()

    def section_changed(self):
        kind=self.section_type.currentText(); self.circle_diameter.setEnabled(kind=='CIRCLE')
        self.width.setEnabled(kind!='CIRCLE'); self.length.setEnabled(kind=='SLOT'); self.height.setEnabled(kind=='RECTANGLE')

    def update_anchor(self):
        base=self.feature.currentData(); self.anchor=deepcopy(base)
        if self.anchor:
            self.anchor.t=self.parameter.value(); self.anchor.angle_deg=self.azimuth.value()
            if self.initial_anchor and anchor_key(base)==anchor_key(self.initial_anchor):
                if self.parameter.value()==self.initial_anchor_controls[0]: self.anchor.t=self.initial_anchor.t
                if self.azimuth.value()==self.initial_anchor_controls[1]: self.anchor.angle_deg=self.initial_anchor.angle_deg
            try:
                xyz,_=resolve_anchor(self.profile,self.anchor); self.xyz_label.setText(' / '.join(f'{v:.3f}' for v in xyz))
            except ValueError as error: self.xyz_label.setText('INVALID: '+str(error))
        elif self.marker:
            xyz,_=interface_pose(self.profile,self.marker); self.xyz_label.setText(' / '.join(f'{v:.3f}' for v in xyz)+' — unanchored legacy record')
        else: self.xyz_label.setText('Select a cavity surface feature')
        self.parameter.setEnabled(bool(base)); self.azimuth.setEnabled(bool(base))
        owner=self.parent()
        if owner and hasattr(owner,'view'): owner.view.highlight_feature(self.anchor)

    def done(self,result):
        owner=self.parent()
        if owner and hasattr(owner,'view'): owner.view.highlight_feature(None)
        super().done(result)

    def submit(self):
        port_id=self.port.currentData() or self.port.currentText()
        marker=deepcopy(self.marker) if self.marker else HydraulicInterface(port_id,'SURFACE')
        marker.hydraulic_port_id=port_id;
        if getattr(self.parent(),'independent',False) and self.marker is None:marker.id=port_id
        marker.surface_anchor=deepcopy(self.anchor)
        try:
            if not self.anchor and not self.marker: raise ValueError('New hydraulic interfaces require a surface anchor')
            vector=tuple(w.value() for w in self.vector)
            if self.marker and vector==self.original_vector: vector=interface_pose(self.profile,self.marker)[1]
            vector=normalized(vector)
            if self.anchor:
                marker.interface_type='SURFACE'
                xyz,_=resolve_anchor(self.profile,self.anchor); marker.z_mm=xyz[2]; marker.r_mm=math.hypot(*xyz[:2])
            if self.marker and self.marker.direction and tuple(w.value() for w in self.vector)==self.original_vector:
                original=self.marker.direction
                if math.isclose(math.sqrt(sum(v*v for v in original)),1,abs_tol=1e-12) and sum(a*b for a,b in zip(original,vector))>0:
                    vector=original
            marker.direction=vector
            values=(self.section_type.currentText(),self.circle_diameter.value(),self.width.value(),self.length.value(),self.height.value())
            marker.section=deepcopy(self.marker.section) if self.marker and self.marker.section and values==self.original_section else ChannelSection(*values)
            marker.section_rotation_deg=self.marker.section_rotation_deg if self.marker and self.rotation.value()==self.original_preview[0] else self.rotation.value()
            marker.preview_length_mm=self.marker.preview_length_mm if self.marker and self.preview_length.value()==self.original_preview[1] else self.preview_length.value()
            marker.validate({p.id for p in self.ports})
        except ValueError as error: self.feedback.setText(str(error)); return
        self.result_marker=marker; self.accept()


class CavityEditor(QDialog):
    def __init__(self, ports=None, physical=None, parent=None, cavity_definition=None, cavity_library=None, save_callback=None):
        super().__init__(parent)
        self.independent=cavity_library is not None or cavity_definition is not None
        self.cavity_library=cavity_library;self.save_callback=save_callback
        self.cavity_definition=deepcopy(cavity_definition)
        self.result_cavity=None
        if self.cavity_definition is not None:
            physical=self.cavity_definition.physical();ports=self.cavity_definition.editor_ports()
        self.setLocale(QLocale.c())
        self.setWindowTitle('Cavity Profile — Four-view Surface Editor V1.5')
        self.setWindowFlags(self.windowFlags()|Qt.WindowMaximizeButtonHint|Qt.WindowMinimizeButtonHint)
        self.resize(1500,900)
        self.ports = deepcopy(ports or [])
        self.physical = deepcopy(physical or PhysicalDefinition())
        self.profile = self.physical.cavity_profile or CavityProfile([ProfileVertex(0,0),ProfileVertex(10,0)])
        self.interfaces = self.physical.hydraulic_interfaces
        self.result_physical = None
        self.selected_id = None
        self.selected_port_id = None
        self.surface_place_mode = False
        self.updating = False
        root = QVBoxLayout(self)
        if self.independent:
            metadata=QFormLayout();self.cavity_name=QLineEdit(self.cavity_definition.name if self.cavity_definition else '')
            self.cavity_description=QLineEdit(self.cavity_definition.description if self.cavity_definition else '')
            metadata.addRow('Cavity name (required)',self.cavity_name);metadata.addRow('Description',self.cavity_description)
            if self.cavity_definition:metadata.addRow('ID / revision',QLabel(f'{self.cavity_definition.id} / {self.cavity_definition.revision}'))
            root.addLayout(metadata)
        heading = QHBoxLayout()
        self.cavity_type = QComboBox()
        self.cavity_type.addItems(['REVOLVED_PROFILE'] if self.independent else ['REVOLVED_PROFILE', 'NONE'])
        heading.addWidget(QLabel('Cavity Type'))
        heading.addWidget(self.cavity_type)
        heading.addWidget(QLabel('Z → (mm) • Y ↑ (mm) • Z=0 mounting face • positive Z into manifold • Revolve axis: Y = 0'))
        heading.addStretch()
        root.addLayout(heading)
        body = QHBoxLayout()
        self.interface_labels={}
        self.view = CavitySketchView(self.profile, self.interfaces,self.interface_labels)
        self.view.lock_endpoints=True
        self.surface_views = {label:CavitySurfaceView(label) for label in ('XZ','XY','ISO')}
        self.four_views = QSplitter(Qt.Vertical)
        top=QSplitter(Qt.Horizontal); top.addWidget(self.view); top.addWidget(self.surface_views['XY'])
        bottom=QSplitter(Qt.Horizontal); bottom.addWidget(self.surface_views['XZ']); bottom.addWidget(self.surface_views['ISO'])
        self.four_views.addWidget(top); self.four_views.addWidget(bottom)
        self.four_views.setStretchFactor(0,1); self.four_views.setStretchFactor(1,1)
        self.four_views.setSizes([400,400]); top.setSizes([500,500]); bottom.setSizes([500,500])
        body.addWidget(self.four_views, 1)
        for preview in self.surface_views.values():
            preview.anchor_requested.connect(self.place_surface_port)
            preview.port_selected.connect(self.select_surface_port)
            preview.port_edit_requested.connect(self.edit_surface_port)
            preview.escape_requested.connect(self.cancel_action)
        properties = QWidget()
        properties.setMinimumWidth(460)
        properties.setMaximumWidth(560)
        side = QVBoxLayout(properties)
        self.vertices_panel=CollapsiblePanel('Theoretical Vertices'); side.addWidget(self.vertices_panel,1)
        self.points = QTableWidget(0, 6)
        self.points.setObjectName('cavityPointTable')
        self.points.setLocale(QLocale.c())
        self.points.setHorizontalHeaderLabels(['#','Z (mm)','Y (mm)','R_fillet (mm)','L_chamfer (mm)','θ_chamfer (°)'])
        self.points.verticalHeader().hide()
        self.points.setSelectionBehavior(QTableWidget.SelectRows)
        self.points.setSelectionMode(QTableWidget.SingleSelection)
        self.points.setItemDelegate(PointNumberDelegate(self.points))
        self.points.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.points.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for column in (3,4,5):
            self.points.horizontalHeader().setSectionResizeMode(column,QHeaderView.ResizeToContents)
        self.points.setSortingEnabled(False)
        self.vertices_panel.content_layout.addWidget(self.points,1)
        actions=QHBoxLayout(); self.add_button=QPushButton('Add Point'); self.add_button.clicked.connect(lambda:self.set_mode(True)); actions.addWidget(self.add_button)
        for label,callback in [('Insert After Selected',self.insert_point),('Delete Selected Point',self.delete_point)]:
            button=QPushButton(label); button.clicked.connect(callback); actions.addWidget(button)
        self.vertices_panel.content_layout.addLayout(actions)
        self.correct_button=QPushButton('Explicitly set endpoint Y = 0'); self.correct_button.clicked.connect(self.correct_endpoints)
        self.vertices_panel.content_layout.addWidget(self.correct_button)
        self.interface_group=CollapsiblePanel('Hydraulic Interfaces')
        group_layout=self.interface_group.content_layout
        self.interface_contents = QWidget()
        marker_layout = QVBoxLayout(self.interface_contents)
        marker_layout.setContentsMargins(0, 0, 0, 0)
        self.markers = QTableWidget(0, 2)
        self.markers.setHorizontalHeaderLabels(['Interface' if self.independent else 'Port ID', 'Type / Z (mm)'])
        self.markers.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.markers.setMaximumHeight(125)
        self.markers.setSelectionBehavior(QTableWidget.SelectRows)
        self.markers.setSelectionMode(QTableWidget.SingleSelection)
        self.markers.setEditTriggers(QTableWidget.NoEditTriggers)
        marker_layout.addWidget(self.markers)
        self.add_port = QPushButton('Add Port — pick cavity surface')
        self.add_port.clicked.connect(self.begin_surface_port); marker_layout.addWidget(self.add_port)
        marker_buttons = QHBoxLayout()
        for label, callback in [('Edit Selected Interface', self.edit_marker), ('Remove Selected Interface', self.remove_marker)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            marker_buttons.addWidget(button)
        marker_layout.addLayout(marker_buttons)
        group_layout.addWidget(self.interface_contents)
        side.addWidget(self.interface_group,1)
        content=QSplitter(Qt.Horizontal); body.removeWidget(self.four_views)
        content.addWidget(self.four_views); content.addWidget(properties); content.setStretchFactor(0,1)
        content.setSizes([1000,480]); body.addWidget(content)
        root.addLayout(body, 1)
        toolbar = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(['Draw mode', 'Edit mode'])
        self.mode.setCurrentIndex(0 if self.physical.cavity_profile is None else 1)
        self.mode.currentIndexChanged.connect(self.mode_changed)
        toolbar.addWidget(QLabel('Mode'))
        toolbar.addWidget(self.mode)
        fit=QPushButton('Fit'); fit.clicked.connect(self.fit_views); toolbar.addWidget(fit)
        self.preview = QPushButton('Revolve Preview')
        self.preview.setCheckable(True)
        self.preview.toggled.connect(self.set_preview)
        toolbar.addWidget(self.preview)
        self.snap = QComboBox()
        self.snap.addItems(['Snap OFF', '0.1 mm', '0.5 mm', '1.0 mm'])
        self.snap.setCurrentIndex(2)
        self.snap.currentIndexChanged.connect(lambda index: setattr(self.view, 'snap_increment', [0, .1, .5, 1][index]))
        toolbar.addWidget(self.snap)
        root.addLayout(toolbar)
        self.validity = QLabel()
        self.warnings = QLabel()
        self.warnings.setWordWrap(True)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        root.addWidget(self.validity)
        root.addWidget(self.warnings)
        root.addWidget(self.feedback)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save_button=buttons.button(QDialogButtonBox.Save)
        if self.independent:
            save_new=buttons.addButton('Save As New',QDialogButtonBox.ActionRole)
            save_new.clicked.connect(lambda:self.submit(save_as_new=True))
        buttons.accepted.connect(self.submit)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.view.point_selected.connect(self.select_point)
        self.view.profile_changed.connect(self.profile_changed)
        self.view.message.connect(self.feedback.setText)
        self.view.marker_requested.connect(self.place_marker)
        self.view.marker_selected.connect(self.select_marker)
        self.view.marker_edit_requested.connect(self.edit_marker)
        self.view.escape_requested.connect(self.cancel_action)
        self.points.itemChanged.connect(self.table_edit)
        self.points.currentCellChanged.connect(self.table_selection_changed)
        self.markers.currentCellChanged.connect(self.marker_selection_changed)
        self.cavity_type.currentTextChanged.connect(self.type_changed)
        self.mode_changed()
        self.refresh_markers()
        self.profile_changed()
        self.view.fit_profile()

    def showEvent(self, event):
        super().showEvent(event)
        self.fit_views()
        QTimer.singleShot(0,self.fit_views)

    def fit_views(self):
        self.view.fit_profile()
        for preview in self.surface_views.values(): preview.fit()

    def refresh_surface_views(self):
        try:
            surface = revolved_surface(self.profile) if not self.profile.validation_errors(revolved=True) else None
        except ValueError: surface = None
        for preview in self.surface_views.values():
            preview.interface_labels=self.interface_labels
            preview.set_geometry(self.profile,surface,self.interfaces,self.selected_port_id)

    def begin_surface_port(self):
        if not self.independent and len(self.interfaces)>=len(self.ports):
            self.feedback.setText('All schematic ports already have an interface'); return
        if self.profile.validation_errors(revolved=True):
            self.feedback.setText('Create a valid cavity profile before picking a surface'); return
        self.view.marker_mode=False; self.surface_place_mode=True
        for preview in self.surface_views.values(): preview.place_mode=True; preview.setCursor(Qt.CrossCursor); preview.update()
        self.feedback.setText('Add Port: click the cavity surface in ISO, XZ or XY; Escape cancels')

    def end_surface_placement(self):
        self.surface_place_mode=False
        for preview in self.surface_views.values(): preview.place_mode=False; preview.unsetCursor(); preview.update()

    def place_surface_port(self,anchor):
        self.end_surface_placement()
        if self.independent:
            self.ports=[PortDefinition(m.id,f'Interface {index+1}',required=False) for index,m in enumerate(self.interfaces)]
            self.ports.append(PortDefinition(new_id(),f'Interface {len(self.interfaces)+1}',required=False))
        dialog=InterfaceDialog(self.ports,self.interfaces,parent=self,profile=self.profile,anchor=anchor)
        if dialog.exec()==QDialog.Accepted:
            self.interfaces.append(dialog.result_marker)
            self.view.rebuild(); self.refresh_markers(); self.profile_changed()
            self.select_surface_port(dialog.result_marker.id)

    def select_surface_port(self,marker_id):
        self.view.select_marker(marker_id)
        if self.selected_port_id!=marker_id:
            self.select_marker(marker_id)  # Invalid/hidden anchors remain editable from the table.

    def edit_surface_port(self,marker_id):
        self.select_surface_port(marker_id); self.edit_marker()

    def keyPressEvent(self, event):
        # QDialog's default Escape rejects the entire editor. Child dialogs still
        # handle Escape normally because they receive their own key events.
        if event.key() == Qt.Key_Escape:
            self.cancel_action()
            event.accept()
        else:
            super().keyPressEvent(event)

    def cancel_action(self):
        if self.surface_place_mode:
            self.end_surface_placement(); self.feedback.setText('Surface port placement cancelled')
            return
        if self.view.marker_mode:
            self.view.marker_mode = False
            self.feedback.setText('Interface placement cancelled')
        elif self.view.dragging_id:
            self.view.cancel_drag()
            self.feedback.setText('Point drag cancelled')
        elif self.view.add_mode:
            self.set_mode(False)
            self.feedback.setText('Edit mode — committed points retained')
        else:
            self.view.scene().clearSelection()
            self.points.clearSelection()
            self.select_point('')
        self.view.insert_after = None
        self.view.clear_preview()
        self.view.update_cursor()

    def mode_changed(self):
        self.end_surface_placement()
        self.view.set_draw_mode(self.mode.currentIndex() == 0)

    def set_mode(self, draw):
        self.mode.setCurrentIndex(0 if draw else 1)
        self.mode_changed()

    def type_changed(self):
        enabled = self.cavity_type.currentText() != 'NONE'
        self.view.lock_endpoints=enabled
        self.view.setEnabled(enabled)
        self.points.setEnabled(enabled)
        self.interface_group.setEnabled(enabled)
        self.profile_changed()

    def refresh_points(self):
        self.updating = True
        scroll = self.points.verticalScrollBar().value()
        self.points.setRowCount(len(self.profile.vertices))
        for row, vertex in enumerate(self.profile.vertices):
            corner = vertex.corner
            values = [str(row + 1), numeric_text(vertex.z), numeric_text(vertex.r),
                      numeric_text(corner.radius_mm) if corner.type == 'FILLET' else '0',
                      numeric_text(corner.length_mm) if corner.type == 'CHAMFER' else '0',
                      numeric_text(corner.angle_deg) if corner.type == 'CHAMFER' else '']
            for col, value in enumerate(values):
                item = self.points.item(row, col)
                if item is None:
                    item = QTableWidgetItem()
                    self.points.setItem(row, col, item)
                item.setText(value)
                item.setData(Qt.UserRole, vertex.id)
                flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
                if col and not (col==2 and row in (0,len(self.profile.vertices)-1) and self.cavity_type.currentText()=='REVOLVED_PROFILE') and (col != 5 or corner.type == 'CHAMFER'):
                    flags |= Qt.ItemIsEditable
                item.setFlags(flags)
                item.setForeground(self.points.palette().color(QPalette.Disabled,QPalette.Text) if col == 5 and corner.type != 'CHAMFER' else self.points.palette().color(QPalette.Text))
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item.setToolTip(f'Theoretical vertex {vertex.id}' if col < 3 else
                                'Fillet radius; positive values replace the chamfer' if col == 3 else
                                'Incoming setback; positive values replace the fillet' if col == 4 else
                                'Activate a chamfer to edit its angle')
        self.points.verticalScrollBar().setValue(scroll)
        self.updating = False
        self.select_point(self.selected_id or '')

    def select_point(self, vertex_id):
        self.selected_id = vertex_id or None
        self.updating = True
        if vertex_id:
            row = next(i for i, v in enumerate(self.profile.vertices) if v.id == vertex_id)
            if self.points.currentRow() != row or not self.points.selectionModel().isRowSelected(row):
                self.points.setCurrentCell(row, max(1, self.points.currentColumn()))
                self.points.selectRow(row)
        else:
            self.points.clearSelection()
            self.points.setCurrentCell(-1, -1)
        self.updating = False

    def table_selection_changed(self, row, col, previous_row, previous_col):
        if self.updating:
            return
        item = self.points.item(row, 0)
        self.view.select_vertex(item.data(Qt.UserRole) if item else None)

    def table_edit(self, item):
        if self.updating:
            return
        vertex_id = item.data(Qt.UserRole)
        vertex = self.profile.vertex(vertex_id)
        col = item.column()
        try:
            value = float(item.text())  # Deliberately accepts periods, never locale commas.
            if not math.isfinite(value):
                raise ValueError('Value must be finite')
            if col==2 and vertex_id in (self.profile.vertices[0].id,self.profile.vertices[-1].id):
                raise ValueError('Endpoint Y is locked; explicitly correct legacy endpoints to zero')
            if col in (1, 2):
                self.profile.edit_point(vertex_id, value if col == 1 else vertex.z,
                                        value if col == 2 else vertex.r)
            elif col in (3, 4):
                if value < 0:
                    raise ValueError('Corner dimensions cannot be negative')
                if value > 0:
                    if col == 3:
                        corner = Corner('FILLET', radius_mm=value)
                    else:
                        angle = vertex.corner.angle_deg if vertex.corner.type == 'CHAMFER' else 45
                        corner = Corner('CHAMFER', length_mm=value, angle_deg=angle)
                    self.profile.set_corner(vertex_id, corner)
                elif vertex.corner.type == ('FILLET' if col == 3 else 'CHAMFER'):
                    self.profile.set_corner(vertex_id, Corner())
            elif col == 5:
                if vertex.corner.type != 'CHAMFER':
                    raise ValueError('Activate a chamfer before editing its angle')
                self.profile.set_corner(vertex_id, Corner('CHAMFER', length_mm=vertex.corner.length_mm, angle_deg=value))
            self.feedback.clear()
        except ValueError as error:
            self.feedback.setText(f'Edit rejected: {error}')
        self.view.rebuild(vertex_id)
        self.profile_changed()

    def profile_changed(self):
        if self.independent:
            self.ports=[PortDefinition(m.id,f'Interface {index+1}',required=False) for index,m in enumerate(self.interfaces)]
            self.interface_labels.clear();self.interface_labels.update({m.id:f'Interface {index+1}' for index,m in enumerate(self.interfaces)})
            for m in self.interfaces:
                label=self.view.marker_labels.get(m.id)
                if label:label.setText(self.interface_labels[m.id])
        errors = [] if self.cavity_type.currentText() == 'NONE' else self.profile.validation_errors(revolved=True)
        self.validity.setText('INVALID: ' + errors[0] if errors else 'VALID')
        interface_errors=[]
        if self.independent:
            for m in self.interfaces:
                try:
                    if m.surface_anchor is None:raise ValueError('Interface needs explicit surface reattachment')
                    resolve_anchor(self.profile,m.surface_anchor)
                except ValueError as error:interface_errors.append(str(error))
        self.save_button.setEnabled(not errors and not interface_errors)
        self.correct_button.setVisible(self.cavity_type.currentText()=='REVOLVED_PROFILE' and any(v.r!=0 for v in self.profile.vertices[::max(1,len(self.profile.vertices)-1)]))
        self.validity.setStyleSheet('color: #b3261e' if errors else 'color: #267343')
        physical = PhysicalDefinition(self.cavity_type.currentText(), self.profile, self.interfaces)
        self.warnings.setText('; '.join(physical.warnings(self.ports)+interface_errors))
        self.refresh_points()
        self.refresh_surface_views()
        self.refresh_markers(self.selected_port_id)

    def insert_point(self):
        if not self.selected_id:
            self.feedback.setText('Select the point preceding the insertion')
            return
        selected = self.selected_id
        if selected==self.profile.vertices[-1].id:
            self.feedback.setText('Insert before the last axis endpoint by selecting the preceding vertex'); return
        self.set_mode(True)
        self.view.insert_after = selected
        self.feedback.setText('Click the canvas to insert after the selected point')

    def delete_point(self):
        if not self.selected_id:
            return
        if self.selected_id in (self.profile.vertices[0].id,self.profile.vertices[-1].id):
            self.feedback.setText('Axis endpoints cannot be deleted; edit Z or delete an intermediate point'); return
        try:
            self.profile.delete_point(self.selected_id)
        except ValueError as error:
            self.feedback.setText(f'Deletion rejected: {error}')
            return
        self.view.insert_after = None
        self.selected_id = None
        self.view.rebuild()
        self.profile_changed()

    def correct_endpoints(self):
        candidate=deepcopy(self.profile)
        candidate.vertices[0].r=candidate.vertices[-1].r=0
        try: candidate.features()
        except ValueError as error: self.feedback.setText('Endpoint correction rejected: '+str(error)); return
        self.profile.vertices[0].r=self.profile.vertices[-1].r=0
        self.view.rebuild(self.selected_id); self.profile_changed()

    def set_preview(self, enabled):
        self.view.mirrored = enabled
        self.view.refresh_path()
        self.view.fit_profile()
        self.feedback.setText('Mirrored cross-section preview; no 3D solid or CAD kernel' if enabled else '')

    def refresh_markers(self, selected=None):
        self.markers.blockSignals(True)
        self.markers.setRowCount(len(self.interfaces))
        for row, marker in enumerate(self.interfaces):
            try:
                xyz,_=interface_pose(self.profile,marker)
                status=f'{marker.interface_type} / {xyz[2]:g}'
            except ValueError: status='INVALID anchor'
            for col, text in enumerate([self.interface_labels.get(marker.id,marker.hydraulic_port_id),status]):
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, marker.id)
                item.setToolTip(marker.id)
                self.markers.setItem(row, col, item)
            if marker.id == selected:
                self.markers.selectRow(row)
        self.markers.blockSignals(False)

    def select_marker(self, marker_id):
        self.selected_port_id=marker_id or None
        for preview in self.surface_views.values(): preview.selected_port=self.selected_port_id; preview.update()
        self.markers.blockSignals(True)
        self.markers.clearSelection()
        self.markers.setCurrentCell(-1, -1)
        for row, marker in enumerate(self.interfaces):
            if marker.id == marker_id:
                self.markers.setCurrentCell(row, 0)
                self.markers.selectRow(row)
                break
        self.markers.blockSignals(False)

    def marker_selection_changed(self, row, col, previous_row, previous_col):
        item = self.markers.item(row, 0)
        if item:
            self.select_surface_port(item.data(Qt.UserRole))

    def begin_marker(self):
        self.end_surface_placement()
        if len(self.interfaces) >= len(self.ports):
            self.feedback.setText('All schematic ports already have an interface')
            return
        self.view.marker_mode = True
        self.view.clear_preview()
        self.view.update_cursor()
        self.feedback.setText('Click the sketch to place a hydraulic interface marker; Escape cancels')

    def place_marker(self, z, r):
        anchor=legacy_surface_anchor(self.profile,HydraulicInterface('','RADIAL',z,r))
        if anchor is None:
            for patch in surface_patches(self.profile):
                for t in (0,1):
                    if math.dist(patch.evaluate(t)[0],(z,r))<1e-7:
                        anchor=deepcopy(patch.anchor); anchor.t=t; anchor.angle_deg=90; break
                if anchor: break
        self.view.marker_mode=False
        self.view.update_cursor()
        if anchor is None:
            self.feedback.setText('Select a point on the evaluated cavity surface')
            return
        dialog = InterfaceDialog(self.ports, self.interfaces, parent=self,profile=self.profile,anchor=anchor)
        if dialog.exec() == QDialog.Accepted:
            self.interfaces.append(dialog.result_marker)
            self.refresh_markers(dialog.result_marker.id)
            self.view.rebuild(self.selected_id)
            self.profile_changed()
        self.view.marker_mode = False
        self.view.update_cursor()

    def edit_marker(self):
        row = self.markers.currentRow()
        if row < 0:
            return
        dialog = InterfaceDialog(self.ports, self.interfaces, self.interfaces[row], parent=self,profile=self.profile)
        if dialog.exec() == QDialog.Accepted:
            self.interfaces[row] = dialog.result_marker
            self.refresh_markers(dialog.result_marker.id)
            self.view.rebuild(self.selected_id)
            self.profile_changed()

    def remove_marker(self):
        row = self.markers.currentRow()
        if row < 0:
            return
        del self.interfaces[row]
        self.refresh_markers()
        self.view.rebuild(self.selected_id)
        self.profile_changed()

    def submit(self,save_as_new=False):
        physical = PhysicalDefinition() if self.cavity_type.currentText() == 'NONE' else PhysicalDefinition('REVOLVED_PROFILE', self.profile, self.interfaces)
        try:
            physical.validate(self.ports,strict=True)
        except ValueError as error:
            self.feedback.setText(str(error))
            return
        self.result_physical = deepcopy(physical)
        if self.independent:
            cavity=deepcopy(self.cavity_definition) if self.cavity_definition else CavityDefinition('',deepcopy(self.profile))
            cavity.name=self.cavity_name.text().strip();cavity.description=self.cavity_description.text()
            cavity.profile=deepcopy(self.profile);cavity.interfaces=deepcopy(self.interfaces);cavity.geometry_type=physical.cavity_type
            if save_as_new:cavity=cavity.duplicate(cavity.name)
            try:
                cavity.validate()
                if self.save_callback is None and self.cavity_library is None:raise ValueError('Choose a cavity library before saving')
                self.result_cavity=self.save_callback(cavity) if self.save_callback else self.cavity_library.save(cavity)
                if self.result_cavity is None:return
            except (ValueError,OSError) as error:self.feedback.setText(str(error));return
        self.accept()
