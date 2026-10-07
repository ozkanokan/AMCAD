from PySide6.QtWidgets import QGraphicsEllipseItem
from PySide6.QtCore import Qt
from PySide6.QtGui import QPen, QColor, QBrush


class PortItem(QGraphicsEllipseItem):
    def __init__(self, node_id, label, parent, canvas):
        super().__init__(-5, -5, 10, 10, parent)
        self.node_id = node_id
        self.canvas = canvas
        self.setPen(QPen(QColor('#17657a'), 1.6))
        self.idle_color = '#23465c' if parent.kind == 'junction' else '#ffffff'
        self.setBrush(QBrush(QColor(self.idle_color)))
        self.setZValue(5)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CrossCursor)
        self.setToolTip(label + '\nClick, then click another port to connect. Escape cancels.')

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
