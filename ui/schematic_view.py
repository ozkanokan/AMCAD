import math
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsPathItem
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath
from ui.component_item import ComponentItem
from ui.connection_item import ConnectionItem
from ui.port_item import PortItem
from core.line_geometry import endpoint, routed_geometry, crossing_points
from core.geometry import SIDE_VECTORS, LEAD_LENGTH
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
        self.draft_controls = []
        self.draft_axis = 0
        self.preview_item = None
        self.alignment_guides=[]
        self.pan_start = None
        self.setScene(QGraphicsScene(self))
        self.setSceneRect(-5000,-5000,10000,10000)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.rebuild()
        self.centerOn(0,0)

    def rebuild(self, selected=()):
        self.clear_alignment()
        self.pending_node = None
        self.preview_item = None
        self.draft_controls = []
        self.port_items = {}; self.component_items = {}; self.wires = {}
        self.scene().clear()
        for instance in self.project.instances.values():
            item = ComponentItem(instance, self.project.effective_definition(instance.id), self)
            self.scene().addItem(item)
            self.component_items[instance.id] = item
            self.port_items.update(item.ports)
            item.setSelected(instance.id in selected)
        for connection in self.project.connections.values():
            item = ConnectionItem(connection,self)
            self.scene().addItem(item)
            self.wires[connection.id] = item
        self.update_wires()

    def update_wires(self, refresh_handles=True):
        for wire in self.wires.values(): wire.update_path()
        crossings = crossing_points({key:wire.connection.schematic_geometry['points'] for key,wire in self.wires.items()})
        for rank,key in enumerate(sorted(self.wires)):
            wire=self.wires[key]
            wire.crossings=crossings[key]; wire.setZValue(-1+rank*.00001)
            wire.render_crossings()
            if refresh_handles: wire.refresh_handles()
        for item in self.component_items.values(): item.update()
        for port in self.port_items.values(): port.refresh()

    def selected_instances(self):
        return [i.instance.id for i in self.scene().selectedItems() if isinstance(i,ComponentItem)]

    def selected_connections(self):
        return [i.connection.id for i in self.scene().selectedItems() if isinstance(i,ConnectionItem)]

    def port_clicked(self, node_id):
        if self.project.port_occupied(node_id):
            self.message.emit('Port already has a line (occupied); use an explicit junction to branch')
            return
        if self.pending_node is None:
            self.pending_node = node_id
            self.draft_controls = []
            _, side = endpoint(self.project,node_id)
            self.draft_axis = 0 if SIDE_VECTORS[side][0] else 1
            self.preview_item=QGraphicsPathItem()
            self.preview_item.setPen(QPen(QColor('#009eaa'),2,Qt.DashLine))
            self.preview_item.setZValue(20)
            self.preview_item.setAcceptedMouseButtons(Qt.NoButton)
            self.scene().addItem(self.preview_item)
            self.port_items[node_id].setBrush(QBrush(QColor('#f5b942')))
            self.update_preview(self.port_items[node_id].scenePos())
            self.message.emit('Draw Line: click empty canvas for bends; click a free port to finish. Escape/right-click cancels.')
            return
        source = self.pending_node
        try:
            self.project.connect(source,node_id,self.draft_controls)
        except ValueError as error:
            self.message.emit(str(error)); return
        self.cancel_connection()
        selected = self.selected_instances()
        self.rebuild(selected)
        self.changed.emit()
        self.message.emit('Line completed. Use an explicit junction to branch; crossings are disconnected.')

    def projected_cursor(self, pos):
        a,side=endpoint(self.project,self.pending_node)
        vector=SIDE_VECTORS[side]
        lead=[a[0]+vector[0]*LEAD_LENGTH,a[1]+vector[1]*LEAD_LENGTH]
        start=self.draft_controls[-1] if self.draft_controls else lead
        point=list(start); point[self.draft_axis]=pos.x() if self.draft_axis==0 else pos.y()
        if not self.draft_controls:
            if sum((point[i]-lead[i])*vector[i] for i in (0,1))<0: point=lead
        return point

    def add_bend(self,pos):
        point=self.projected_cursor(pos)
        if not self.draft_controls or point!=self.draft_controls[-1]:
            self.draft_controls.append(point)
            self.draft_axis=1-self.draft_axis
        self.update_preview(pos)

    def update_preview(self,pos):
        if self.pending_node is None: return
        a,side=endpoint(self.project,self.pending_node)
        target=next((item for item in self.scene().items(pos) if isinstance(item,PortItem)),None)
        if target and target.node_id!=self.pending_node and not self.project.port_occupied(target.node_id):
            b,b_side=endpoint(self.project,target.node_id)
            points=routed_geometry(a,side,b,b_side,self.draft_controls)['points']
        else:
            vector=SIDE_VECTORS[side]
            points=[a,(a[0]+vector[0]*LEAD_LENGTH,a[1]+vector[1]*LEAD_LENGTH),*self.draft_controls,self.projected_cursor(pos)]
        path=QPainterPath(QPointF(*points[0]))
        for point in points[1:]: path.lineTo(QPointF(*point))
        self.preview_item.setPath(path)

    def cancel_connection(self):
        if self.pending_node in self.port_items:
            port = self.port_items[self.pending_node]
            port.setBrush(QBrush(QColor(port.idle_color)))
        self.pending_node = None
        self.draft_controls=[]
        if self.preview_item is not None:
            self.scene().removeItem(self.preview_item); self.preview_item=None

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
        if self.pending_node is not None and event.button()==Qt.RightButton:
            self.clear_alignment();self.cancel_connection(); self.message.emit('Line cancelled'); event.accept(); return
        if self.pending_node is not None and event.button()==Qt.LeftButton:
            pos=self.mapToScene(event.position().toPoint())
            items=[i for i in self.scene().items(pos) if i is not self.preview_item]
            port=next((i for i in items if isinstance(i,PortItem)),None)
            if port: self.port_clicked(port.node_id)
            elif not items: self.add_bend(pos)
            else: self.message.emit('Place a bend on empty canvas or choose a free target port')
            event.accept(); return
        if event.button()==Qt.MiddleButton:
            self.pan_start = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor); event.accept()
        else: super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.pending_node is not None:
            self.update_preview(self.mapToScene(event.position().toPoint()))
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
            self.clear_alignment();self.cancel_connection(); self.message.emit('Line cancelled'); event.accept()
        else: super().keyPressEvent(event)

    def fit_content(self):
        if self.component_items:
            rect = self.scene().itemsBoundingRect().adjusted(-70,-70,70,70)
            self.fitInView(rect,Qt.KeepAspectRatio)
            if self.transform().m11()>2:
                self.resetTransform(); self.scale(2,2); self.centerOn(rect.center())
        else:
            self.resetTransform(); self.centerOn(0,0)

    def clear_alignment(self):
        for item in self.alignment_guides:
            if item.scene():self.scene().removeItem(item)
        self.alignment_guides=[]

    def aligned_position(self,item,position):
        """Snap each axis independently: port matches precede center matches."""
        self.clear_alignment()
        if len(self.selected_instances())>1:return position
        tolerance=6/max(self.transform().m11(),.01)
        offsets=[item.mapToScene(port.pos())-item.pos() for port in item.ports.values()]
        ports=[position+offset for offset in offsets]
        others=[other for other in self.component_items.values() if other is not item and not other.isSelected()]
        result=QPointF(position)
        for axis in (0,1):
            coordinate=lambda p:p.x() if axis==0 else p.y()
            matches=[]
            for other in others:
                targets=[other.mapToScene(port.pos()) for port in other.ports.values()]
                for source in ports:
                    for target in targets:
                        delta=coordinate(target)-coordinate(source)
                        if abs(delta)<=tolerance:matches.append((0,abs(delta),delta,coordinate(target)))
                delta=coordinate(other.pos())-coordinate(position)
                if abs(delta)<=tolerance:matches.append((1,abs(delta),delta,coordinate(other.pos())))
            if matches:
                _,_,delta,line=min(matches)
                if axis==0:result.setX(position.x()+delta)
                else:result.setY(position.y()+delta)
                pen=QPen(QColor('#169cad'),1,Qt.DashLine);pen.setCosmetic(True)
                guide=self.scene().addLine(line,-5000,line,5000,pen) if axis==0 else self.scene().addLine(-5000,line,5000,line,pen)
                guide.setAcceptedMouseButtons(Qt.NoButton);guide.setZValue(-.5);self.alignment_guides.append(guide)
        return result
