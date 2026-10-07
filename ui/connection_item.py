from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsItem
from PySide6.QtGui import QPainterPath, QPainterPathStroker, QPen, QColor


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
        a = self.canvas.port_items[self.connection.from_node_id].scenePos()
        b = self.canvas.port_items[self.connection.to_node_id].scenePos()
        path = QPainterPath(a)
        mid = (a.x()+b.x())/2
        path.lineTo(mid, a.y())
        path.lineTo(mid, b.y())
        path.lineTo(b)
        self.setPath(path)

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(12)
        return stroker.createStroke(self.path())

    def paint(self, painter, option, widget=None):
        self.setPen(QPen(QColor('#009eaa' if self.isSelected() else '#365f79'), 3 if self.isSelected() else 2))
        super().paint(painter,option,widget)
