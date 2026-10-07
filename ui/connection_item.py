from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsItem
from PySide6.QtGui import QPainterPath, QPainterPathStroker, QPen, QColor
from core.geometry import rotated_side, wire_points


class ConnectionItem(QGraphicsPathItem):
    def __init__(self, connection, canvas):
        super().__init__()
        self.connection = connection
        self.canvas = canvas
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setZValue(-1)
        self.setToolTip('Routing connection · select and Delete to remove\nCrossings do not create connectivity')
        self.update_path()

    def update_path(self):
        source = self.canvas.port_items[self.connection.from_node_id]
        target = self.canvas.port_items[self.connection.to_node_id]
        a, b = source.scenePos(), target.scenePos()
        a_side = rotated_side(source.side, source.parentItem().instance.rotation)
        b_side = rotated_side(target.side, target.parentItem().instance.rotation)
        path = QPainterPath(a)
        for x, y in wire_points((a.x(), a.y()), a_side, (b.x(), b.y()), b_side)[1:]:
            path.lineTo(x, y)
        self.setPath(path)

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(12)
        return stroker.createStroke(self.path())

    def paint(self, painter, option, widget=None):
        self.setPen(QPen(QColor('#009eaa' if self.isSelected() else '#365f79'), 3 if self.isSelected() else 2))
        super().paint(painter,option,widget)
