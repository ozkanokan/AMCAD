from copy import deepcopy
import math
from PySide6.QtCore import Qt, QLocale, QTimer
from PySide6.QtGui import QDoubleValidator, QColor, QPalette
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QWidget,
    QLabel, QPushButton, QComboBox, QDoubleSpinBox, QDialogButtonBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QStyledItemDelegate, QLineEdit, QGroupBox, QSplitter)
from core.cavity import CavityProfile, Corner, PhysicalDefinition, HydraulicInterface
from ui.cavity_sketch_view import CavitySketchView
from core.cavity_surface import (SurfaceAnchor, ChannelSection, normalized, surface_patches,
    resolve_anchor, interface_pose, revolved_surface, anchor_key)
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


class InterfaceDialog(QDialog):
    def __init__(self, ports, interfaces, marker=None, z=0, r=0, parent=None, profile=None, anchor=None):
        super().__init__(parent)
        self.setLocale(QLocale.c())
        self.setWindowTitle('Hydraulic Interface Marker')
        self.marker = deepcopy(marker)
        self.profile = profile
        self.anchor = deepcopy(anchor if anchor is not None else marker.surface_anchor if marker else None)
        self.result_marker = None
        form = QFormLayout(self)
        self.port = QComboBox()
        occupied = {i.hydraulic_port_id for i in interfaces if marker is None or i.id != marker.id}
        self.port.addItems([p.id for p in ports if p.id not in occupied])
        self.kind = QComboBox()
        self.kind.addItems(['AXIAL', 'RADIAL', 'SURFACE'])
        self.z = number()
        self.r = number(0)  # Internal r remains the persisted radial-coordinate field.
        self.diameter = number(.000001)
        self.use_r = QCheckBox('Store Y position')
        self.use_r.setChecked(True)
        self.direction = QComboBox()
        self.direction.addItems(['UNSPECIFIED', 'AXIAL_POSITIVE', 'AXIAL_NEGATIVE', 'RADIAL'])
        self.z.setValue(z)
        self.r.setValue(r)
        self.diameter.setValue(4)
        if marker:
            self.port.setCurrentText(marker.hydraulic_port_id)
            self.kind.setCurrentText(marker.interface_type)
            self.z.setValue(marker.z_mm)
            self.r.setValue(marker.r_mm or 0)
            self.use_r.setChecked(marker.r_mm is not None)
            self.diameter.setValue(marker.nominal_connection_diameter_mm)
            self.direction.setCurrentText(marker.preferred_direction)
        if anchor is not None:
            xyz, normal = resolve_anchor(profile, anchor)
            self.kind.setCurrentText('SURFACE')
            self.z.setValue(xyz[2]); self.r.setValue(math.hypot(xyz[0], xyz[1]))
        self.original_numbers = {name: getattr(self, name).value() for name in ('z', 'r', 'diameter')}
        self.use_r.toggled.connect(self.r.setEnabled)
        self.r.setEnabled(self.use_r.isChecked())
        for label, widget in [('Schematic Port ID', self.port), ('Interface Type', self.kind),
                              ('Z (mm)', self.z), ('Y (mm)', self.r), ('', self.use_r),
                              ('Nominal Diameter (mm)', self.diameter), ('Preferred Direction', self.direction)]:
            form.addRow(label, widget)
        self.feature = QComboBox()
        try: patches = surface_patches(profile) if profile is not None else []
        except ValueError: patches = []
        self.feature.addItem('Legacy fixed position', None)
        for index, patch in enumerate(patches):
            self.feature.addItem(f'{index+1}: {patch.anchor.kind} ({patch.anchor.vertex_id[:8]})', patch.anchor)
        if self.anchor is not None:
            match = next((i for i in range(1,self.feature.count()) if anchor_key(self.feature.itemData(i))==anchor_key(self.anchor)), None)
            if match is None:
                self.feature.addItem('INVALID original anchor (choose a new feature)', self.anchor)
                match = self.feature.count()-1
            self.feature.setCurrentIndex(match)
        form.addRow('Surface feature', self.feature)
        self.parameter = number(0,1); self.azimuth = number(-360000,360000)
        self.parameter.setValue(self.anchor.t if self.anchor else .5)
        self.azimuth.setValue(self.anchor.angle_deg if self.anchor else 0)
        self.initial_anchor=deepcopy(self.anchor)
        self.initial_anchor_controls=(self.parameter.value(),self.azimuth.value())
        anchor_row = QHBoxLayout(); anchor_row.addWidget(QLabel('Along [0–1]')); anchor_row.addWidget(self.parameter)
        anchor_row.addWidget(QLabel('Angle (°)')); anchor_row.addWidget(self.azimuth)
        form.addRow('Surface anchor', anchor_row)
        self.xyz_label = QLabel(); form.addRow('Resolved XYZ (mm)', self.xyz_label)
        try: vector = interface_pose(profile, marker)[1] if marker else normal if anchor else (0,0,1)
        except ValueError: vector = marker.direction or (0,0,1)
        self.vector = [number(-1e6,1e6) for _ in range(3)]
        vector_row = QHBoxLayout()
        for name, widget, value in zip(('dx','dy','dz'),self.vector,vector):
            widget.setValue(value); vector_row.addWidget(QLabel(name)); vector_row.addWidget(widget)
        form.addRow('Channel direction', vector_row)
        self.section_type = QComboBox(); self.section_type.addItems(['CIRCLE','SLOT','RECTANGLE'])
        section = marker.section if marker and marker.section else ChannelSection(diameter_mm=self.diameter.value())
        self.section_type.setCurrentText(section.type)
        self.width = number(.000001); self.length = number(.000001); self.height = number(.000001)
        self.circle_diameter = number(.000001); self.circle_diameter.setValue(section.diameter_mm)
        self.width.setValue(section.width_mm); self.length.setValue(section.length_mm); self.height.setValue(section.height_mm)
        form.addRow('Cross section',self.section_type)
        section_row = QHBoxLayout()
        for name,widget in [('Diameter',self.circle_diameter),('Width',self.width),('Overall length',self.length),('Height',self.height)]:
            section_row.addWidget(QLabel(name)); section_row.addWidget(widget)
        form.addRow('Section sizes (mm)',section_row)
        self.rotation = number(-360000,360000); self.preview_length = number(.000001)
        self.rotation.setValue(marker.section_rotation_deg if marker else 0)
        self.preview_length.setValue(marker.preview_length_mm if marker else 10)
        form.addRow('Section rotation (°)',self.rotation)
        form.addRow('Preview length (mm)',self.preview_length)
        form.addRow(QLabel('Preview only — no drilling depth, trimming or Boolean intersection'))
        self.original_extended = (tuple(w.value() for w in self.vector),self.section_type.currentText(),
                                  self.width.value(),self.length.value(),self.height.value(),self.diameter.value(),self.circle_diameter.value())
        self.original_preview=(self.rotation.value(),self.preview_length.value())
        if not self.anchor and not (marker and marker.section):
            self.diameter.valueChanged.connect(self.circle_diameter.setValue)
        self.feature.currentIndexChanged.connect(self.update_anchor)
        self.parameter.valueChanged.connect(self.update_anchor); self.azimuth.valueChanged.connect(self.update_anchor)
        self.section_type.currentTextChanged.connect(self.section_changed)
        self.section_changed(); self.update_anchor()
        self.feedback = QLabel()
        form.addRow(self.feedback)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.submit)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.ports = ports

    def section_changed(self):
        kind=self.section_type.currentText()
        self.circle_diameter.setEnabled(kind=='CIRCLE')
        self.width.setEnabled(kind!='CIRCLE'); self.length.setEnabled(kind=='SLOT'); self.height.setEnabled(kind=='RECTANGLE')

    def update_anchor(self):
        base=self.feature.currentData()
        self.anchor=deepcopy(base)
        if self.anchor:
            self.anchor.t=self.parameter.value(); self.anchor.angle_deg=self.azimuth.value()
            if self.initial_anchor and anchor_key(base)==anchor_key(self.initial_anchor):
                if self.parameter.value()==self.initial_anchor_controls[0]: self.anchor.t=self.initial_anchor.t
                if self.azimuth.value()==self.initial_anchor_controls[1]: self.anchor.angle_deg=self.initial_anchor.angle_deg
            try:
                xyz,_=resolve_anchor(self.profile,self.anchor)
                self.xyz_label.setText(' / '.join(f'{v:.8g}' for v in xyz))
            except ValueError as error: self.xyz_label.setText('INVALID: '+str(error))
        else: self.xyz_label.setText('Legacy: X=0, Y and Z use fixed position fields')
        self.parameter.setEnabled(bool(base)); self.azimuth.setEnabled(bool(base))
        self.z.setEnabled(not bool(base)); self.r.setEnabled(not bool(base) and self.use_r.isChecked())

    def submit(self):
        marker = HydraulicInterface(self.port.currentText(), self.kind.currentText(), self.z.value(),
                                    self.r.value() if self.use_r.isChecked() else None,
                                    self.diameter.value(), self.direction.currentText())
        if self.marker:
            marker.id = self.marker.id
            # Opening and accepting a marker must not round existing stored data
            # to the numeric widget's display precision.
            for name, field in [('z', 'z_mm'), ('r', 'r_mm'), ('diameter', 'nominal_connection_diameter_mm')]:
                if (name != 'r' or self.use_r.isChecked() == (self.marker.r_mm is not None)) and getattr(self, name).value() == self.original_numbers[name]:
                    setattr(marker, field, getattr(self.marker, field))
        marker.surface_anchor=deepcopy(self.anchor)
        if self.anchor:
            try:
                xyz,_=resolve_anchor(self.profile,self.anchor)
                marker.z_mm=xyz[2]; marker.r_mm=math.hypot(xyz[0],xyz[1])
            except ValueError: pass  # Retain and flag unresolved anchors; explicit reattachment is available.
        try:
            vector=normalized(tuple(w.value() for w in self.vector))
        except ValueError as error:
            self.feedback.setText(str(error)); return
        extended=(tuple(w.value() for w in self.vector),self.section_type.currentText(),
                  self.width.value(),self.length.value(),self.height.value(),self.diameter.value(),self.circle_diameter.value())
        vector_changed=extended[0]!=self.original_extended[0]
        section_changed=extended[1:]!=self.original_extended[1:]
        marker.direction=vector if self.anchor or vector_changed or self.marker and self.marker.direction is not None else None
        marker.section=ChannelSection(self.section_type.currentText(),self.circle_diameter.value(),self.width.value(),self.length.value(),self.height.value()) if self.anchor or section_changed or self.marker and self.marker.section is not None else None
        if self.marker and not vector_changed: marker.direction=deepcopy(self.marker.direction)
        if self.marker and not section_changed: marker.section=deepcopy(self.marker.section)
        marker.section_rotation_deg=self.rotation.value(); marker.preview_length_mm=self.preview_length.value()
        if self.marker:
            if self.rotation.value()==self.original_preview[0]: marker.section_rotation_deg=self.marker.section_rotation_deg
            if self.preview_length.value()==self.original_preview[1]: marker.preview_length_mm=self.marker.preview_length_mm
        try:
            marker.validate({p.id for p in self.ports})
        except ValueError as error:
            self.feedback.setText(str(error))
            return
        self.result_marker = marker
        self.accept()


class CavityEditor(QDialog):
    def __init__(self, ports, physical=None, parent=None):
        super().__init__(parent)
        self.setLocale(QLocale.c())
        self.setWindowTitle('Cavity Profile — Four-view Surface Editor V1.4')
        self.resize(1500, 900)
        self.ports = deepcopy(ports)
        self.physical = deepcopy(physical or PhysicalDefinition())
        self.profile = self.physical.cavity_profile or CavityProfile()
        self.interfaces = self.physical.hydraulic_interfaces
        self.result_physical = None
        self.selected_id = None
        self.selected_port_id = None
        self.surface_place_mode = False
        self.updating = False
        root = QVBoxLayout(self)
        heading = QHBoxLayout()
        self.cavity_type = QComboBox()
        self.cavity_type.addItems(['REVOLVED_PROFILE', 'NONE'])
        heading.addWidget(QLabel('Cavity Type'))
        heading.addWidget(self.cavity_type)
        heading.addWidget(QLabel('Z → (mm) • Y ↑ (mm) • Z=0 mounting face • positive Z into manifold • Revolve axis: Y = 0'))
        heading.addStretch()
        root.addLayout(heading)
        body = QHBoxLayout()
        self.view = CavitySketchView(self.profile, self.interfaces)
        self.surface_views = {label:CavitySurfaceView(label) for label in ('XZ','XY','ISO')}
        self.four_views = QSplitter(Qt.Vertical)
        top=QSplitter(Qt.Horizontal); top.addWidget(self.view); top.addWidget(self.surface_views['XZ'])
        bottom=QSplitter(Qt.Horizontal); bottom.addWidget(self.surface_views['XY']); bottom.addWidget(self.surface_views['ISO'])
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
        side.addWidget(QLabel('Theoretical vertices — edit values directly; R is fillet radius'))
        self.points = QTableWidget(0, 6)
        self.points.setObjectName('cavityPointTable')
        self.points.setLocale(QLocale.c())
        self.points.setHorizontalHeaderLabels(['#', 'Z (mm)', 'Y (mm)', 'R (mm)', 'Chamfer (mm)', 'Angle (°)'])
        self.points.verticalHeader().hide()
        self.points.setSelectionBehavior(QTableWidget.SelectRows)
        self.points.setSelectionMode(QTableWidget.SingleSelection)
        self.points.setItemDelegate(PointNumberDelegate(self.points))
        self.points.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.points.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.points.setSortingEnabled(False)
        side.addWidget(self.points, 1)
        self.interface_group = QGroupBox('Hydraulic Interface Markers')
        self.interface_group.setCheckable(True)
        self.interface_group.setChecked(True)
        group_layout = QVBoxLayout(self.interface_group)
        self.interface_contents = QWidget()
        marker_layout = QVBoxLayout(self.interface_contents)
        marker_layout.setContentsMargins(0, 0, 0, 0)
        self.markers = QTableWidget(0, 2)
        self.markers.setHorizontalHeaderLabels(['Port ID', 'Type / Z (mm)'])
        self.markers.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.markers.setMaximumHeight(125)
        self.markers.setSelectionBehavior(QTableWidget.SelectRows)
        self.markers.setSelectionMode(QTableWidget.SingleSelection)
        self.markers.setEditTriggers(QTableWidget.NoEditTriggers)
        marker_layout.addWidget(self.markers)
        add_marker = QPushButton('Place Interface Marker')
        add_marker.clicked.connect(self.begin_marker)
        marker_layout.addWidget(add_marker)
        self.add_port = QPushButton('Add Port — pick cavity surface')
        self.add_port.clicked.connect(self.begin_surface_port); marker_layout.addWidget(self.add_port)
        marker_buttons = QHBoxLayout()
        for label, callback in [('Edit Selected Interface', self.edit_marker), ('Remove Selected Interface', self.remove_marker)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            marker_buttons.addWidget(button)
        marker_layout.addLayout(marker_buttons)
        group_layout.addWidget(self.interface_contents)
        self.interface_group.toggled.connect(self.interface_contents.setVisible)
        side.addWidget(self.interface_group)
        content=QSplitter(Qt.Horizontal); body.removeWidget(self.four_views)
        content.addWidget(self.four_views); content.addWidget(properties); content.setStretchFactor(0,1)
        content.setSizes([1000,480]); body.addWidget(content)
        root.addLayout(body, 1)
        toolbar = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(['Draw mode', 'Edit mode'])
        self.mode.setCurrentIndex(0 if not self.profile.vertices else 1)
        self.mode.currentIndexChanged.connect(self.mode_changed)
        toolbar.addWidget(QLabel('Mode'))
        toolbar.addWidget(self.mode)
        self.add_button = QPushButton('Add Point')
        self.add_button.clicked.connect(lambda: self.set_mode(True))
        toolbar.addWidget(self.add_button)
        for label, callback in [('Insert After Selected', self.insert_point), ('Delete Point', self.delete_point), ('Fit', self.fit_views)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            toolbar.addWidget(button)
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
            surface = revolved_surface(self.profile) if not self.profile.validation_errors() else None
        except ValueError: surface = None
        for preview in self.surface_views.values():
            preview.set_geometry(self.profile,surface,self.interfaces,self.selected_port_id)

    def begin_surface_port(self):
        if len(self.interfaces)>=len(self.ports):
            self.feedback.setText('All schematic ports already have an interface'); return
        if self.profile.validation_errors():
            self.feedback.setText('Create a valid cavity profile before picking a surface'); return
        self.view.marker_mode=False; self.surface_place_mode=True
        for preview in self.surface_views.values(): preview.place_mode=True; preview.setCursor(Qt.CrossCursor); preview.update()
        self.feedback.setText('Add Port: click the cavity surface in ISO, XZ or XY; Escape cancels')

    def end_surface_placement(self):
        self.surface_place_mode=False
        for preview in self.surface_views.values(): preview.place_mode=False; preview.unsetCursor(); preview.update()

    def place_surface_port(self,anchor):
        self.end_surface_placement()
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
                if col and (col != 5 or corner.type == 'CHAMFER'):
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
        errors = [] if self.cavity_type.currentText() == 'NONE' else self.profile.validation_errors()
        self.validity.setText('INVALID: ' + errors[0] if errors else 'VALID')
        self.validity.setStyleSheet('color: #b3261e' if errors else 'color: #267343')
        physical = PhysicalDefinition(self.cavity_type.currentText(), self.profile, self.interfaces)
        self.warnings.setText('; '.join(physical.warnings(self.ports)))
        self.refresh_points()
        self.refresh_surface_views()
        self.refresh_markers(self.selected_port_id)

    def insert_point(self):
        if not self.selected_id:
            self.feedback.setText('Select the point preceding the insertion')
            return
        selected = self.selected_id
        self.set_mode(True)
        self.view.insert_after = selected
        self.feedback.setText('Click the canvas to insert after the selected point')

    def delete_point(self):
        if not self.selected_id:
            return
        try:
            self.profile.delete_point(self.selected_id)
        except ValueError as error:
            self.feedback.setText(f'Deletion rejected: {error}')
            return
        self.view.insert_after = None
        self.selected_id = None
        self.view.rebuild()
        self.profile_changed()

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
            for col, text in enumerate([marker.hydraulic_port_id,status]):
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, marker.id)
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
        dialog = InterfaceDialog(self.ports, self.interfaces, z=z, r=r, parent=self,profile=self.profile)
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

    def submit(self):
        physical = PhysicalDefinition() if self.cavity_type.currentText() == 'NONE' else PhysicalDefinition('REVOLVED_PROFILE', self.profile, self.interfaces)
        try:
            physical.validate(self.ports)
        except ValueError as error:
            self.feedback.setText(str(error))
            return
        self.result_physical = deepcopy(physical)
        self.accept()
