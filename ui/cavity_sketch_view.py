"""Dedicated Z-Y sketch scene. One scene unit is one millimetre; persisted Y is r."""
import math
from copy import deepcopy
from PySide6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsEllipseItem,
    QGraphicsItem, QGraphicsPathItem, QGraphicsPolygonItem, QGraphicsSimpleTextItem)
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QPainter, QPainterPath, QPainterPathStroker, QPen, QColor, QPolygonF
from core.cavity import snapped, point


def profile_path(profile, mirror=False):
    path = QPainterPath()
    try:
        pieces = profile.pieces()
    except ValueError:
        pieces = [{'kind': 'line', 'start': point(a), 'end': point(b)}
                  for a, b in zip(profile.vertices, profile.vertices[1:])]
    if not pieces:
        return path
    if mirror:
        from PySide6.QtGui import QTransform
        return QTransform.fromScale(1, -1).map(profile_path(profile))
    first = pieces[0].get('start', pieces[0].get('entry'))
    path.moveTo(first[0], -first[1])
    for piece in pieces:
        if piece['kind'] == 'line':
            path.lineTo(piece['end'][0], -piece['end'][1])
        else:
            z, y = piece['center']
            radius = piece['radius']
            path.arcTo(QRectF(z-radius, -y-radius, 2*radius, 2*radius),
                       piece['start_deg'], piece['sweep_deg'])
    return path


def dimension_number(value):
    text = format(value, '.6g')
    return text + '.0' if '.' not in text and 'e' not in text.lower() else text


def corner_dimensions(profile):
    """Presentation leaders target actual derived geometry, never the sharp vertex."""
    result = []
    for vertex, feature in zip(profile.vertices, profile.features()):
        if feature['kind'] == 'arc':
            angle = math.radians(feature['start_deg'] + feature['sweep_deg']/2)
            z, y = feature['center']
            target = (z + feature['radius']*math.cos(angle), y + feature['radius']*math.sin(angle))
            text = 'R' + dimension_number(vertex.corner.radius_mm)
        elif feature['kind'] == 'chamfer':
            target = tuple((a+b)/2 for a, b in zip(feature['entry'], feature['exit']))
            text = f'{dimension_number(vertex.corner.length_mm)} × {vertex.corner.angle_deg:.6g}°'
        else:
            continue
        result.append({'vertex_id': vertex.id, 'kind': feature['kind'], 'target': target, 'text': text})
    return result


class ProfilePointItem(QGraphicsEllipseItem):
    def __init__(self, vertex, view):
        super().__init__(-4, -4, 8, 8)
        self.vertex = vertex
        self.view = view
        self.ready = False
        flags = QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemSendsGeometryChanges | QGraphicsItem.ItemIgnoresTransformations
        if not view.add_mode:
            flags |= QGraphicsItem.ItemIsMovable
        self.setFlags(flags)
        self.setAcceptHoverEvents(True)
        self.setPos(vertex.z, -vertex.r)
        self.setZValue(5)
        self.setPen(QPen(QColor('#17657a'), 0))
        self.setBrush(QColor('white'))
        self.setCursor(Qt.PointingHandCursor if view.add_mode else Qt.SizeAllCursor)
        self.update_tooltip()
        self.ready = True

    def update_tooltip(self):
        self.setToolTip(f'Theoretical vertex\nZ={self.vertex.z:g} mm; Y={self.vertex.r:g} mm\n{self.vertex.id}')

    def itemChange(self, change, value):
        if self.ready and change == QGraphicsItem.ItemPositionChange:
            z, y = snapped(value.x(), -value.y(), self.view.snap_increment)
            try:
                self.view.profile.edit_point(self.vertex.id, z, y)
            except ValueError as error:
                self.view.message.emit(f'Edit rejected: {error}')
                return self.pos()
            return QPointF(z, -y)
        if self.ready and change == QGraphicsItem.ItemPositionHasChanged:
            self.update_tooltip()
            self.view.refresh_path()
            self.view.profile_changed.emit()
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        self.view.hovered_id = self.vertex.id
        self.view.refresh_construction()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.view.hovered_id = None
        self.view.refresh_construction()
        super().hoverLeaveEvent(event)

    def paint(self, painter, option, widget=None):
        self.setBrush(QColor('#5ad5cd' if self.isSelected() else 'white'))
        super().paint(painter, option, widget)
        if self.isSelected() or self.view.hovered_id == self.vertex.id:
            painter.setPen(QPen(QColor('#17657a'), 1))
            painter.drawEllipse(QRectF(-6, -6, 12, 12))


class InterfaceMarkerItem(QGraphicsPolygonItem):
    def __init__(self, interface):
        super().__init__(QPolygonF([QPointF(0, -6), QPointF(6, 0), QPointF(0, 6), QPointF(-6, 0)]))
        self.interface = interface
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIgnoresTransformations)
        self.setPos(interface.z_mm, -(interface.r_mm or 0))
        self.setPen(QPen(QColor('#b26a20'), 1))
        self.setBrush(QColor('#ffc66b'))
        self.setZValue(4)
        self.setToolTip(f'{interface.hydraulic_port_id} ({interface.interface_type})\nDouble-click to edit interface')


class CavitySketchView(QGraphicsView):
    profile_changed = Signal()
    point_selected = Signal(str)
    message = Signal(str)
    marker_requested = Signal(float, float)
    marker_selected = Signal(str)
    marker_edit_requested = Signal()
    escape_requested = Signal()

    AXIS_LABEL = 'Revolve axis: Y = 0; Z → (mm)'
    DATUM_LABEL = 'Z=0 mounting face; Y ↑ (mm)'

    def __init__(self, profile, interfaces):
        super().__init__()
        self.profile = profile
        self.interfaces = interfaces
        self.snap_increment = .5
        self.add_mode = not bool(profile.vertices)
        self.insert_after = None
        self.marker_mode = False
        self.mirrored = False
        self.point_items = {}
        self.marker_items = {}
        self.path_item = None
        self.mirror_item = None
        self.construction_item = None
        self.preview_item = None
        self.dimensions = []
        self.dimension_layout = []
        self.hovered_id = None
        self.pan_start = None
        self.dragging_id = None
        self.drag_before = None
        self.setScene(QGraphicsScene(self))
        self.setSceneRect(-1000, -1000, 2000, 2000)
        self.setMouseTracking(True)
        self.setRenderHint(QPainter.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.scene().selectionChanged.connect(self.selection_changed)
        self.scale(20, 20)
        self.centerOn(15, -7)
        self.rebuild()

    def update_cursor(self):
        self.setCursor(Qt.CrossCursor if self.add_mode or self.marker_mode else Qt.ArrowCursor)

    def set_draw_mode(self, draw):
        self.add_mode = draw
        self.marker_mode = False
        self.insert_after = None
        self.clear_preview()
        for item in self.point_items.values():
            item.setFlag(QGraphicsItem.ItemIsMovable, not draw)
            item.setCursor(Qt.PointingHandCursor if draw else Qt.SizeAllCursor)
        self.update_cursor()

    def selection_changed(self):
        points = [i for i in self.scene().selectedItems() if isinstance(i, ProfilePointItem)]
        markers = [i for i in self.scene().selectedItems() if isinstance(i, InterfaceMarkerItem)]
        self.point_selected.emit(points[0].vertex.id if points else '')
        self.marker_selected.emit(markers[0].interface.id if markers else '')
        self.refresh_construction()

    def select_vertex(self, vertex_id):
        self.scene().blockSignals(True)
        self.scene().clearSelection()
        if vertex_id in self.point_items:
            self.point_items[vertex_id].setSelected(True)
        self.scene().blockSignals(False)
        self.selection_changed()

    def select_marker(self, marker_id):
        self.scene().blockSignals(True)
        self.scene().clearSelection()
        if marker_id in self.marker_items:
            self.marker_items[marker_id].setSelected(True)
        self.scene().blockSignals(False)
        self.selection_changed()

    def rebuild(self, selected=None):
        # Scene clear emits selection changes; block them until new UUID handles exist.
        self.scene().blockSignals(True)
        self.point_items = {}
        self.marker_items = {}
        self.hovered_id = None
        self.scene().clear()
        self.path_item = QGraphicsPathItem()
        self.path_item.setPen(QPen(QColor('#23465c'), 2))
        # Cosmetic pens retain their engineering line weight while zooming.
        pen = self.path_item.pen()
        pen.setCosmetic(True)
        self.path_item.setPen(pen)
        self.path_item.setAcceptedMouseButtons(Qt.NoButton)
        self.scene().addItem(self.path_item)
        self.mirror_item = QGraphicsPathItem()
        self.mirror_item.setPen(QPen(QColor('#849eac'), 0, Qt.DashLine))
        self.mirror_item.setAcceptedMouseButtons(Qt.NoButton)
        self.scene().addItem(self.mirror_item)
        self.construction_item = QGraphicsPathItem()
        self.construction_item.setPen(QPen(QColor('#8c9fac'), 0, Qt.DashLine))
        self.construction_item.setAcceptedMouseButtons(Qt.NoButton)
        self.scene().addItem(self.construction_item)
        self.preview_item = QGraphicsPathItem()
        self.preview_item.setPen(QPen(QColor('#318896'), 0, Qt.DashLine))
        self.preview_item.setAcceptedMouseButtons(Qt.NoButton)
        self.scene().addItem(self.preview_item)
        for vertex in self.profile.vertices:
            item = ProfilePointItem(vertex, self)
            self.point_items[vertex.id] = item
            self.scene().addItem(item)
            item.setSelected(vertex.id == selected)
        self.draw_interfaces()
        self.scene().blockSignals(False)
        self.refresh_path()
        self.selection_changed()

    def refresh_path(self):
        self.path_item.setPath(profile_path(self.profile))
        self.mirror_item.setPath(profile_path(self.profile, True) if self.mirrored else QPainterPath())
        try:
            self.dimensions = corner_dimensions(self.profile)
        except ValueError:
            self.dimensions = []
        self.refresh_construction()
        self.viewport().update()

    def refresh_construction(self):
        if self.construction_item is None:
            return
        path = QPainterPath()
        selected = {i.vertex.id for i in self.point_items.values() if i.isSelected()}
        if self.hovered_id:
            selected.add(self.hovered_id)
        try:
            features = self.profile.features()
        except ValueError:
            features = []
        for vertex, feature in zip(self.profile.vertices, features):
            if vertex.id in selected and feature['kind'] != 'sharp':
                path.moveTo(feature['entry'][0], -feature['entry'][1])
                path.lineTo(vertex.z, -vertex.r)
                path.lineTo(feature['exit'][0], -feature['exit'][1])
        self.construction_item.setPath(path)
        self.viewport().update()

    def draw_interfaces(self):
        for interface in self.interfaces:
            marker = InterfaceMarkerItem(interface)
            self.marker_items[interface.id] = marker
            self.scene().addItem(marker)
            text = self.scene().addSimpleText(f'{interface.hydraulic_port_id} ({interface.interface_type})')
            text.setFlag(QGraphicsItem.ItemIgnoresTransformations)
            text.setPos(interface.z_mm + .5, -(interface.r_mm or 0) - .5)
            text.setBrush(QColor('#8b4f15'))
            text.setAcceptedMouseButtons(Qt.NoButton)

    def clear_preview(self):
        if self.preview_item is not None:
            self.preview_item.setPath(QPainterPath())

    def mousePressEvent(self, event):
        pos = self.mapToScene(event.position().toPoint())
        if event.button() == Qt.MiddleButton:
            self.pan_start = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            if self.marker_mode:
                z, y = snapped(pos.x(), -pos.y(), self.snap_increment)
                self.marker_mode = False
                self.update_cursor()
                self.marker_requested.emit(z, y)
                event.accept()
                return
            hits = self.items(event.position().toPoint())
            hit = next((i for i in hits if isinstance(i, ProfilePointItem)), None)
            marker = next((i for i in hits if isinstance(i, InterfaceMarkerItem)), None)
            if hit and not self.add_mode:
                self.dragging_id = hit.vertex.id
                self.drag_before = deepcopy(self.profile.to_dict())
            elif not hit and not marker and self.add_mode:
                z, y = snapped(pos.x(), -pos.y(), self.snap_increment)
                try:
                    vertex = self.profile.add_point(z, y, self.insert_after)
                except ValueError as error:
                    self.message.emit(f'Point not added: {error}')
                    event.accept()
                    return
                inserting = self.insert_after is not None
                self.insert_after = None
                self.rebuild(vertex.id)
                self.profile_changed.emit()
                if inserting:
                    self.clear_preview()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and not self.marker_mode:
            hits = self.items(event.position().toPoint())
            marker = next((i for i in hits if isinstance(i, InterfaceMarkerItem)), None)
            vertex = next((i for i in hits if isinstance(i, ProfilePointItem)), None)
            if marker and not vertex:
                self.select_marker(marker.interface.id)
                self.marker_edit_requested.emit()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        if self.pan_start is not None:
            pos = event.position().toPoint()
            delta = pos - self.pan_start
            self.pan_start = pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        if self.add_mode and not self.marker_mode and self.profile.vertices:
            pos = self.mapToScene(event.position().toPoint())
            z, y = snapped(pos.x(), -pos.y(), self.snap_increment)
            vertex = self.profile.vertex(self.insert_after) if self.insert_after else self.profile.vertices[-1]
            path = QPainterPath(QPointF(vertex.z, -vertex.r))
            path.lineTo(z, -y)
            self.preview_item.setPath(path)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.clear_preview()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self.pan_start = None
            self.update_cursor()
            event.accept()
        else:
            super().mouseReleaseEvent(event)
            self.dragging_id = None
            self.drag_before = None

    def cancel_drag(self):
        if self.dragging_id and self.drag_before:
            # Restore every committed theoretical coordinate, retaining object/UUID identity.
            for saved in self.drag_before['vertices']:
                vertex = self.profile.vertex(saved['id'])
                vertex.z, vertex.r = saved['z'], saved['r']
            selected = self.dragging_id
            grabber = self.scene().mouseGrabberItem()
            if grabber:
                grabber.ungrabMouse()
            self.dragging_id = None
            self.drag_before = None
            self.rebuild(selected)
            self.profile_changed.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.escape_requested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1/1.15
        if 2 <= self.transform().m11()*factor <= 400:
            self.scale(factor, factor)
        event.accept()

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor('#f4f7fa'))
        step = 1 if self.transform().m11() >= 12 else 5
        painter.setPen(QPen(QColor('#dce5ec'), 0))
        z = math.floor(rect.left()/step)*step
        while z <= rect.right():
            painter.drawLine(QPointF(z, rect.top()), QPointF(z, rect.bottom()))
            z += step
        y = math.floor(rect.top()/step)*step
        while y <= rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += step
        painter.setPen(QPen(QColor('#496478'), 0, Qt.DashLine))
        painter.drawLine(QPointF(rect.left(), 0), QPointF(rect.right(), 0))
        painter.drawLine(QPointF(0, rect.top()), QPointF(0, rect.bottom()))
        painter.save()
        painter.resetTransform()
        painter.setPen(QColor('#304c61'))
        origin = self.mapFromScene(QPointF(0, 0))
        y = max(20, min(self.viewport().height()-10, origin.y()-8))
        painter.drawText(10, y, self.AXIS_LABEL)
        x = max(10, min(self.viewport().width()-200, origin.x()+8))
        painter.drawText(x, 20, self.DATUM_LABEL)
        painter.restore()

    def drawForeground(self, painter, rect):
        # Leaders/text in viewport pixels stay legible and noninteractive at any zoom.
        painter.save()
        painter.resetTransform()
        metrics = painter.fontMetrics()
        occupied = []
        obstacles = [self.mapFromScene(QPointF(v.z, -v.r)) for v in self.profile.vertices]
        label_boxes = [item.deviceTransform(self.viewportTransform()).mapRect(item.boundingRect())
                       for item in self.scene().items() if isinstance(item, QGraphicsSimpleTextItem)]
        stroker = QPainterPathStroker()
        stroker.setWidth(14)
        displayed = self.viewportTransform().map(self.path_item.path())
        displayed.addPath(self.viewportTransform().map(self.mirror_item.path()))
        profile_obstacle = stroker.createStroke(displayed)
        self.dimension_layout = []
        margin = 8
        for dimension in self.dimensions:
            z, y = dimension['target']
            target = QPointF(self.mapFromScene(QPointF(z, -y)))
            if not self.viewport().rect().adjusted(-50, -50, 50, 50).contains(target.toPoint()):
                continue
            width = metrics.horizontalAdvance(dimension['text']) + 10
            height = metrics.height() + 4
            candidates = []
            for dy in (-48, 40, -76, 68, -104, 96):
                for dx in (32, -width-32):
                    box = QRectF(target.x()+dx, target.y()+dy-height/2, width, height)
                    box.moveLeft(max(margin, min(self.viewport().width()-width-margin, box.left())))
                    box.moveTop(max(28, min(self.viewport().height()-height-margin, box.top())))
                    score = sum(box.adjusted(-5, -5, 5, 5).intersects(old) for old in occupied)*1000
                    score += 1000 if profile_obstacle.intersects(box) else 0
                    score += sum(box.intersects(label) for label in label_boxes)*1000
                    score += sum(box.adjusted(-8, -8, 8, 8).contains(QPointF(p)) for p in obstacles)*100
                    score += abs(dy)
                    candidates.append((score, box))
            box = min(candidates, key=lambda entry: entry[0])[1]
            occupied.append(box)
            elbow = QPointF(box.left() if box.center().x() > target.x() else box.right(), box.center().y())
            painter.setPen(QPen(QColor('#596b77'), 1))
            painter.drawLine(target, elbow)
            painter.drawLine(elbow, QPointF(box.right() if elbow.x() == box.left() else box.left(), elbow.y()))
            direction = elbow-target
            norm = math.hypot(direction.x(), direction.y()) or 1
            unit = QPointF(direction.x()/norm, direction.y()/norm)
            normal = QPointF(-unit.y(), unit.x())
            painter.setBrush(QColor('#596b77'))
            painter.drawPolygon(QPolygonF([target, target+unit*7+normal*2.5, target+unit*7-normal*2.5]))
            painter.fillRect(box, QColor('#f4f7fa'))
            painter.drawText(box, Qt.AlignCenter, dimension['text'])
            self.dimension_layout.append({'vertex_id': dimension['vertex_id'], 'rect': box, 'target': target})
        painter.restore()

    def fit_profile(self):
        points = [(v.z, v.r) for v in self.profile.vertices] + [(i.z_mm, i.r_mm or 0) for i in self.interfaces]
        if not points:
            return
        zs = [p[0] for p in points] + [0]
        ys = [p[1] for p in points] + [0]
        rect = QRectF(min(zs), -max(ys), max(zs)-min(zs), max(ys)-min(ys))
        if self.mirrored:
            rect.setBottom(max(ys))
        self.fitInView(rect.adjusted(-3, -4, 5, 3), Qt.KeepAspectRatio)
        if self.transform().m11() > 80:
            self.resetTransform()
            self.scale(80, 80)
            self.centerOn(rect.center())
