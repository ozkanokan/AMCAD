from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsItem, QGraphicsEllipseItem, QStyleOptionGraphicsItem, QStyle
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainterPath, QPainterPathStroker, QPen, QColor, QBrush
from core.line_geometry import normalize


class GeometryHandle(QGraphicsEllipseItem):
    def __init__(self,line,index,kind,position):
        super().__init__(-4,-4,8,8,line)
        self.line=line; self.index=index; self.kind=kind
        self.origin=None; self.original=None
        self.setPos(QPointF(*position)); self.setZValue(10)
        self.setBrush(QBrush(QColor('white'))); self.setPen(QPen(QColor('#009eaa'),1.5))
        points=line.connection.schematic_geometry['points']
        horizontal=kind=='segment' and points[index][1]==points[index+1][1]
        self.setCursor(Qt.SizeVerCursor if horizontal else Qt.SizeHorCursor if kind=='segment' else Qt.SizeAllCursor)
        self.setToolTip('Drag line segment' if kind=='segment' else 'Drag line bend')

    def mousePressEvent(self,event):
        self.origin=event.scenePos()
        self.original=[p[:] for p in self.line.connection.schematic_geometry['points']]
        event.accept()

    def mouseMoveEvent(self,event):
        if self.origin is None: return
        delta=event.scenePos()-self.origin
        points=[p[:] for p in self.original]
        i=self.index
        if self.kind=='segment':
            horizontal=points[i][1]==points[i+1][1]
            axis=1 if horizontal else 0
            shift=delta.y() if horizontal else delta.x()
            points[i][axis]+=shift; points[i+1][axis]+=shift
        else:
            old=points[i][:]; points[i]=[old[0]+delta.x(),old[1]+delta.y()]
            for neighbor in (i-1,i+1):
                if neighbor in (0,len(points)-1): continue
                axis=1 if self.original[neighbor][1]==old[1] else 0
                points[neighbor][axis]=points[i][axis]
        # Promote edited interior points to fixed controls; the true port endpoints
        # and mandatory leads are reconstructed independently and cannot be moved.
        self.line.canvas.project.set_line_geometry(self.line.connection.id,normalize(points[1:-1]))
        self.line.canvas.update_wires(refresh_handles=False)
        self.setPos(self.origin+delta)
        event.accept()

    def mouseReleaseEvent(self,event):
        self.origin=None
        self.line.canvas.changed.emit()
        # Defer handle replacement until Qt finishes dispatching this handle's event.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0,self.line.refresh_handles)
        event.accept()


class ConnectionItem(QGraphicsPathItem):
    def __init__(self,connection,canvas):
        super().__init__()
        self.connection=connection; self.canvas=canvas
        self.handles=[]; self.crossings={}; self.logical_path=QPainterPath()
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setZValue(-1)
        self.setToolTip('Line · select to edit segments/bends · Delete Line removes it\nCrossings do not connect')
        self.update_path()

    def update_path(self):
        self.canvas.project.update_line_geometry(self.connection.id)
        points=self.connection.schematic_geometry['points']
        path=QPainterPath(QPointF(*points[0]))
        for p in points[1:]: path.lineTo(QPointF(*p))
        self.logical_path=path
        self.render_crossings()

    def render_crossings(self):
        points=self.connection.schematic_geometry['points']
        path=QPainterPath(QPointF(*points[0]))
        for index,(a,b) in enumerate(zip(points,points[1:])):
            horizontal=a[1]==b[1]
            axis=0 if horizontal else 1
            sign=1 if b[axis]>a[axis] else -1
            crossings=sorted(self.crossings.get(index,[]),key=lambda p:sign*p[axis])
            for ci,c in enumerate(crossings):
                gaps=[abs(c[axis]-a[axis]),abs(b[axis]-c[axis])]
                if ci: gaps.append(abs(c[axis]-crossings[ci-1][axis])/2)
                if ci+1<len(crossings): gaps.append(abs(c[axis]-crossings[ci+1][axis])/2)
                radius=min(6,*gaps)*.9; k=.55228475*radius
                if radius<.5: continue
                if horizontal:
                    before=(c[0]-sign*radius,c[1]); after=(c[0]+sign*radius,c[1])
                    path.lineTo(*before)
                    path.cubicTo(before[0],c[1]-k,c[0]-sign*k,c[1]-radius,c[0],c[1]-radius)
                    path.cubicTo(c[0]+sign*k,c[1]-radius,after[0],c[1]-k,*after)
                else:
                    before=(c[0],c[1]-sign*radius); after=(c[0],c[1]+sign*radius)
                    path.lineTo(*before)
                    path.cubicTo(c[0]+k,before[1],c[0]+radius,c[1]-sign*k,c[0]+radius,c[1])
                    path.cubicTo(c[0]+radius,c[1]+sign*k,c[0]+k,after[1],*after)
            path.lineTo(*b)
        self.setPath(path)

    def clear_handles(self):
        for handle in self.handles:
            scene=handle.scene()
            handle.setParentItem(None)
            if scene: scene.removeItem(handle)
        self.handles=[]

    def refresh_handles(self):
        self.clear_handles()
        if not self.isSelected(): return
        points=self.connection.schematic_geometry['points']
        for index in range(1,len(points)-2):
            a,b=points[index:index+2]
            self.handles.append(GeometryHandle(self,index,'segment',[(a[0]+b[0])/2,(a[1]+b[1])/2]))
        for index in range(2,len(points)-2):
            self.handles.append(GeometryHandle(self,index,'bend',points[index]))
        if not self.handles and len(points) > 2:
            self.handles.append(GeometryHandle(self,1,'bend',points[1]))

    def itemChange(self,change,value):
        result=super().itemChange(change,value)
        if change==QGraphicsItem.ItemSelectedHasChanged: self.refresh_handles()
        return result

    def shape(self):
        stroker=QPainterPathStroker(); stroker.setWidth(12)
        return stroker.createStroke(self.path())

    def paint(self,painter,option,widget=None):
        self.setPen(QPen(QColor('#009eaa' if self.isSelected() else '#365f79'),3 if self.isSelected() else 2))
        option=QStyleOptionGraphicsItem(option)
        option.state &= ~QStyle.State_Selected
        super().paint(painter,option,widget)
