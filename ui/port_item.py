from PySide6.QtWidgets import QGraphicsEllipseItem
from PySide6.QtCore import Qt
from PySide6.QtGui import QPen, QColor, QBrush


class PortItem(QGraphicsEllipseItem):
    def __init__(self, node_id, label, parent, canvas, side):
        super().__init__(-5, -5, 10, 10, parent)
        self.node_id = node_id
        self.canvas = canvas
        self.side = side
        self.setPen(QPen(QColor('#17657a'), 1.6))
        self.idle_color = '#ffffff'
        self.setBrush(QBrush(QColor(self.idle_color)))
        self.setZValue(5)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CrossCursor)
        self.setToolTip(label + '\nDraw Line: click a free port, place bends, then click a free target. Escape cancels.')

    def refresh(self):
        node=self.canvas.project.nodes[self.node_id]
        definition=self.canvas.project.definitions[self.canvas.project.instances[node.instance_id].definition_id]
        required=next(p.required for p in definition.ports if p.id==node.port_id)
        missing=required and not self.canvas.project.port_occupied(self.node_id)
        self.idle_color='#fff1d7' if missing else '#ffffff'
        self.setPen(QPen(QColor('#ad772d' if missing else '#17657a'),1.6))
        self.setBrush(QBrush(QColor('#f5b942' if self.canvas.pending_node==self.node_id else self.idle_color)))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.canvas.port_clicked(self.node_id)
            event.accept()
        else:
            super().mousePressEvent(event)

    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(QColor('#5ad5cd')))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        selected = self.canvas.pending_node == self.node_id
        self.setBrush(QBrush(QColor('#f5b942' if selected else self.idle_color)))
        super().hoverLeaveEvent(event)
