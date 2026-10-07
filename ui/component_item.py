from PySide6.QtWidgets import QGraphicsItem, QGraphicsSimpleTextItem
from PySide6.QtCore import QRectF, Qt, QPointF
from PySide6.QtGui import QColor, QPen, QBrush, QFont, QPolygonF
from ui.geometry import port_positions
from ui.port_item import PortItem


class ComponentItem(QGraphicsItem):
    def __init__(self, instance, definition, canvas):
        super().__init__()
        self.instance = instance
        self.definition = definition
        self.canvas = canvas
        self.ready = False
        self.kind = definition.symbol.get('kind', 'box')
        self.w = definition.symbol.get('width', 110)
        self.h = definition.symbol.get('height', 76)
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemSendsGeometryChanges)
        self.setCursor(Qt.SizeAllCursor)
        self.setPos(instance.x, instance.y)
        self.setRotation(instance.rotation)
        self.setZValue(1)
        label = QGraphicsSimpleTextItem(instance.name, self)
        self.label = label
        label.setFont(QFont('Sans Serif', 10, QFont.DemiBold))
        label.setBrush(QColor('#233847'))
        label.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self.position_label()
        self.ports = {}
        for p in definition.ports:
            node = canvas.project.node_for(instance.id, p.id)
            port = PortItem(node.id, f'{instance.name}.{p.id}', self, canvas, p.side)
            port.setPos(port_positions(definition)[p.id])
            self.ports[node.id] = port
            if self.kind == 'box':
                text = QGraphicsSimpleTextItem(p.display_name, self)
                text.setBrush(QColor('#376078'))
                text.setFont(QFont('Sans Serif', 8))
                pos = port.pos()
                width = text.boundingRect().width()
                if p.side=='LEFT': text.setPos(pos.x()+9,pos.y()-7)
                elif p.side=='RIGHT': text.setPos(pos.x()-width-9,pos.y()-7)
                elif p.side=='TOP': text.setPos(pos.x()-width/2,pos.y()+7)
                else: text.setPos(pos.x()-width/2,pos.y()-21)
        self.setToolTip(f'{instance.name} · {definition.name}\nDouble-click for properties')
        self.ready = True

    def boundingRect(self):
        return QRectF(-self.w/2-7, -self.h/2-7, self.w+14, self.h+14)

    def position_label(self):
        rotation=self.instance.rotation
        height=self.w if rotation in (90,270) else self.h
        x,y=-self.label.boundingRect().width()/2,height/2+18
        x,y=[(x,y),(y,-x),(-x,-y),(-y,x)][int(rotation)//90]
        self.label.setPos(x,y)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        incomplete = not self.canvas.project.is_complete(self.instance.id)
        color = '#168c9d' if self.isSelected() else '#ad772d' if incomplete else '#42576a'
        painter.setPen(QPen(QColor(color), 2 if self.isSelected() else 1.5))
        painter.setBrush(QBrush(QColor('#e8f6f7' if self.isSelected() else '#ffffff')))
        if self.kind=='junction':
            for port in self.ports.values():
                painter.drawLine(0, 0, int(port.pos().x()), int(port.pos().y()))
            painter.setBrush(QColor('#23465c'))
            painter.drawEllipse(QRectF(-6,-6,12,12))
        elif self.kind=='external':
            painter.save()
            painter.rotate({'RIGHT':0,'BOTTOM':90,'LEFT':180,'TOP':270}[self.definition.ports[0].side])
            vertical=self.definition.ports[0].side in {'TOP','BOTTOM'}
            w,h=(self.h/2,self.w/3) if vertical else (self.w/2,self.h/3)
            painter.drawPolygon(QPolygonF([QPointF(-w,0),QPointF(-w/2,-h),QPointF(w,-h),
                                           QPointF(w,h),QPointF(-w/2,h)]))
            painter.restore()
        else:
            painter.drawRect(QRectF(-self.w/2,-self.h/2,self.w,self.h))
            painter.setFont(QFont('Sans Serif', 9))
            painter.drawText(QRectF(-self.w/2+12,-14,self.w-24,28), Qt.AlignCenter, self.definition.name)

    def itemChange(self, change, value):
        if self.ready and change == QGraphicsItem.ItemPositionHasChanged:
            self.instance.x = value.x()
            self.instance.y = value.y()
            self.canvas.update_wires()
        if self.ready and change == QGraphicsItem.ItemRotationHasChanged:
            self.instance.rotation = int(value) % 360
            self.position_label()
            self.canvas.update_wires()
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.canvas.changed.emit()

    def mouseDoubleClickEvent(self, event):
        self.canvas.properties_requested.emit(self.instance.id)
        event.accept()
