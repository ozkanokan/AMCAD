import math
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsItem
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush
from ui.component_item import ComponentItem
from ui.connection_item import ConnectionItem
from ui.component_library import MIME_TYPE


class SchematicView(QGraphicsView):
    changed = Signal()
    message = Signal(str)
    properties_requested = Signal(str)
    component_dropped = Signal(str, float, float)

    def __init__(self, project):
        super().__init__()
        self.project = project
        self.port_items = {}
        self.component_items = {}
        self.wires = {}
        self.pending_node = None
        self.pan_start = None
        self.setScene(QGraphicsScene(self))
        self.setSceneRect(-5000,-5000,10000,10000)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setAcceptDrops(True)
        self.rebuild()
        self.centerOn(0,0)

    def rebuild(self, selected=()):
        self.pending_node = None
        self.port_items = {}; self.component_items = {}; self.wires = {}
        self.scene().clear()
        for instance in self.project.instances.values():
            item = ComponentItem(instance, self.project.definitions[instance.definition_id], self)
            self.scene().addItem(item)
            self.component_items[instance.id] = item
            self.port_items.update(item.ports)
            item.setSelected(instance.id in selected)
        for connection in self.project.connections.values():
            item = ConnectionItem(connection,self)
            self.scene().addItem(item)
            self.wires[connection.id] = item

    def update_wires(self):
        for wire in self.wires.values(): wire.update_path()

    def selected_instances(self):
        return [i.instance.id for i in self.scene().selectedItems() if isinstance(i,ComponentItem)]

    def selected_connections(self):
        return [i.connection.id for i in self.scene().selectedItems() if isinstance(i,ConnectionItem)]

    def port_clicked(self, node_id):
        if self.pending_node is None:
            self.pending_node = node_id
            self.port_items[node_id].setBrush(QBrush(QColor('#f5b942')))
            self.message.emit('Choose the destination port. Escape cancels.')
            return
        source = self.pending_node
        self.cancel_connection()
        try:
            self.project.connect(source,node_id)
        except ValueError as error:
            self.message.emit(str(error)); return
        selected = self.selected_instances()
        self.rebuild(selected)
        self.changed.emit()
        self.message.emit('Connected. Add an explicit junction for a branch; crossings are disconnected.')

    def cancel_connection(self):
        if self.pending_node in self.port_items:
            port = self.port_items[self.pending_node]
            port.setBrush(QBrush(QColor(port.idle_color)))
        self.pending_node = None

    def drawBackground(self, painter, rect):
        painter.fillRect(rect,QColor('#f4f7fa'))
        # Skip the fine grid when zoomed out to avoid expensive invisible detail.
        step = 20 if self.transform().m11() >= .5 else 100
        painter.setPen(QPen(QColor('#dce5ec'),0))
        x = math.floor(rect.left()/step)*step
        while x <= rect.right():
            painter.drawLine(QPointF(x,rect.top()),QPointF(x,rect.bottom())); x += step
        y = math.floor(rect.top()/step)*step
        while y <= rect.bottom():
            painter.drawLine(QPointF(rect.left(),y),QPointF(rect.right(),y)); y += step

    def dragEnterEvent(self,event):
        if event.mimeData().hasFormat(MIME_TYPE): event.acceptProposedAction()
        else: event.ignore()

    def dragMoveEvent(self,event):
        if event.mimeData().hasFormat(MIME_TYPE): event.acceptProposedAction()
        else: event.ignore()

    def dropEvent(self,event):
        definition_id = bytes(event.mimeData().data(MIME_TYPE)).decode()
        pos = self.mapToScene(event.position().toPoint())
        self.component_dropped.emit(definition_id,pos.x(),pos.y())
        event.acceptProposedAction()

    def zoom(self,factor):
        target = self.transform().m11()*factor
        if .15 <= target <= 4: self.scale(factor,factor)

    def wheelEvent(self,event):
        self.zoom(1.15 if event.angleDelta().y()>0 else 1/1.15)
        event.accept()

    def mousePressEvent(self,event):
        if event.button()==Qt.MiddleButton:
            self.pan_start = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor); event.accept()
        else: super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.pan_start is not None:
            pos = event.position().toPoint(); delta = pos-self.pan_start; self.pan_start=pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value()-delta.y())
            event.accept()
        else: super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MiddleButton:
            self.pan_start=None; self.unsetCursor(); event.accept()
        else: super().mouseReleaseEvent(event)

    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Escape:
            self.cancel_connection(); self.message.emit('Connection cancelled'); event.accept()
        else: super().keyPressEvent(event)

    def fit_content(self):
        if self.component_items:
            rect = self.scene().itemsBoundingRect().adjusted(-70,-70,70,70)
            self.fitInView(rect,Qt.KeepAspectRatio)
            if self.transform().m11()>2:
                self.resetTransform(); self.scale(2,2); self.centerOn(rect.center())
        else:
            self.resetTransform(); self.centerOn(0,0)
