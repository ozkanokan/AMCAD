from copy import deepcopy
import math
from PySide6.QtCore import Qt, QLocale
from PySide6.QtGui import QDoubleValidator, QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QWidget,
    QLabel, QPushButton, QComboBox, QDoubleSpinBox, QDialogButtonBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QStyledItemDelegate, QLineEdit, QGroupBox)
from core.cavity import CavityProfile, Corner, PhysicalDefinition, HydraulicInterface
from ui.cavity_sketch_view import CavitySketchView


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
    def __init__(self, ports, interfaces, marker=None, z=0, r=0, parent=None):
        super().__init__(parent)
        self.setLocale(QLocale.c())
        self.setWindowTitle('Hydraulic Interface Marker')
        self.marker = deepcopy(marker)
        self.result_marker = None
        form = QFormLayout(self)
        self.port = QComboBox()
        occupied = {i.hydraulic_port_id for i in interfaces if marker is None or i.id != marker.id}
        self.port.addItems([p.id for p in ports if p.id not in occupied])
        self.kind = QComboBox()
        self.kind.addItems(['AXIAL', 'RADIAL'])
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
        self.original_numbers = {name: getattr(self, name).value() for name in ('z', 'r', 'diameter')}
        self.use_r.toggled.connect(self.r.setEnabled)
        self.r.setEnabled(self.use_r.isChecked())
        for label, widget in [('Schematic Port ID', self.port), ('Interface Type', self.kind),
                              ('Z (mm)', self.z), ('Y (mm)', self.r), ('', self.use_r),
                              ('Nominal Diameter (mm)', self.diameter), ('Preferred Direction', self.direction)]:
            form.addRow(label, widget)
        self.feedback = QLabel()
        form.addRow(self.feedback)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.submit)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.ports = ports

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
        self.setWindowTitle('Cavity Profile — Axisymmetric Sketcher V1.3a')
        self.resize(1260, 760)
        self.ports = deepcopy(ports)
        self.physical = deepcopy(physical or PhysicalDefinition())
        self.profile = self.physical.cavity_profile or CavityProfile()
        self.interfaces = self.physical.hydraulic_interfaces
        self.result_physical = None
        self.selected_id = None
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
        body.addWidget(self.view, 1)
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
        marker_buttons = QHBoxLayout()
        for label, callback in [('Edit Selected Interface', self.edit_marker), ('Remove Selected Interface', self.remove_marker)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            marker_buttons.addWidget(button)
        marker_layout.addLayout(marker_buttons)
        group_layout.addWidget(self.interface_contents)
        self.interface_group.toggled.connect(self.interface_contents.setVisible)
        side.addWidget(self.interface_group)
        body.addWidget(properties)
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
        for label, callback in [('Insert After Selected', self.insert_point), ('Delete Point', self.delete_point), ('Fit', self.view.fit_profile)]:
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
        self.view.fit_profile()

    def keyPressEvent(self, event):
        # QDialog's default Escape rejects the entire editor. Child dialogs still
        # handle Escape normally because they receive their own key events.
        if event.key() == Qt.Key_Escape:
            self.cancel_action()
            event.accept()
        else:
            super().keyPressEvent(event)

    def cancel_action(self):
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
                item.setForeground(QColor('#85909a' if col == 5 and corner.type != 'CHAMFER' else '#243746'))
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
            for col, text in enumerate([marker.hydraulic_port_id, f'{marker.interface_type} / {marker.z_mm:g}']):
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, marker.id)
                self.markers.setItem(row, col, item)
            if marker.id == selected:
                self.markers.selectRow(row)
        self.markers.blockSignals(False)

    def select_marker(self, marker_id):
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
            self.view.select_marker(item.data(Qt.UserRole))

    def begin_marker(self):
        if len(self.interfaces) >= len(self.ports):
            self.feedback.setText('All schematic ports already have an interface')
            return
        self.view.marker_mode = True
        self.view.clear_preview()
        self.view.update_cursor()
        self.feedback.setText('Click the sketch to place a hydraulic interface marker; Escape cancels')

    def place_marker(self, z, r):
        dialog = InterfaceDialog(self.ports, self.interfaces, z=z, r=r, parent=self)
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
        dialog = InterfaceDialog(self.ports, self.interfaces, self.interfaces[row], parent=self)
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
