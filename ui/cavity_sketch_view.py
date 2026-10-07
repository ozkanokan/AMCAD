"""Dedicated Z-R sketch scene. One scene unit is one millimetre."""
import math
from PySide6.QtWidgets import QGraphicsView,QGraphicsScene,QGraphicsEllipseItem,QGraphicsItem,QGraphicsPathItem
from PySide6.QtCore import Qt,Signal,QPointF,QRectF
from PySide6.QtGui import QPainter,QPainterPath,QPen,QColor,QPolygonF
from core.cavity import snapped,point


def profile_path(profile,mirror=False):
    path=QPainterPath()
    try: pieces=profile.pieces()
    except ValueError:
        pieces=[{'kind':'line','start':point(a),'end':point(b)} for a,b in zip(profile.vertices,profile.vertices[1:])]
    if not pieces: return path
    if not mirror:
        first=pieces[0].get('start',pieces[0].get('entry')); path.moveTo(first[0],-first[1])
        for piece in pieces:
            if piece['kind']=='line': path.lineTo(piece['end'][0],-piece['end'][1])
            else:
                z,r=piece['center']; radius=piece['radius']
                path.arcTo(QRectF(z-radius,-r-radius,2*radius,2*radius),piece['start_deg'],piece['sweep_deg'])
    else:
        # Reflect the exact displayed path, without changing the stored profile.
        from PySide6.QtGui import QTransform
        return QTransform.fromScale(1,-1).map(profile_path(profile))
    return path


class ProfilePointItem(QGraphicsEllipseItem):
    def __init__(self,vertex,view):
        super().__init__(-4,-4,8,8)
        self.vertex=vertex; self.view=view; self.ready=False
        self.setFlags(QGraphicsItem.ItemIsMovable|QGraphicsItem.ItemIsSelectable|QGraphicsItem.ItemSendsGeometryChanges|QGraphicsItem.ItemIgnoresTransformations)
        self.setPos(vertex.z,-vertex.r); self.setZValue(5)
        self.setPen(QPen(QColor('#17657a'),0)); self.setBrush(QColor('white'))
        self.setCursor(Qt.SizeAllCursor); self.setToolTip(f'Z={vertex.z:g} mm; R={vertex.r:g} mm\n{vertex.id}')
        self.ready=True

    def itemChange(self,change,value):
        if self.ready and change==QGraphicsItem.ItemPositionChange:
            z,r=snapped(value.x(),-value.y(),self.view.snap_increment)
            try: self.view.profile.edit_point(self.vertex.id,z,r)
            except ValueError as error:
                self.view.message.emit(str(error)); return self.pos()
            return QPointF(z,-r)
        if self.ready and change==QGraphicsItem.ItemPositionHasChanged:
            self.view.refresh_path(); self.view.profile_changed.emit()
        return super().itemChange(change,value)

    def paint(self,painter,option,widget=None):
        self.setBrush(QColor('#5ad5cd' if self.isSelected() else 'white'))
        super().paint(painter,option,widget)


class CavitySketchView(QGraphicsView):
    profile_changed=Signal()
    point_selected=Signal(str)
    message=Signal(str)
    marker_requested=Signal(float,float)

    def __init__(self,profile,interfaces):
        super().__init__()
        self.profile=profile; self.interfaces=interfaces
        self.snap_increment=.5; self.add_mode=True; self.insert_after=None; self.marker_mode=False; self.mirrored=False
        self.point_items={}; self.path_item=None; self.mirror_item=None; self.pan_start=None
        self.setScene(QGraphicsScene(self)); self.setSceneRect(-1000,-1000,2000,2000)
        self.setRenderHint(QPainter.Antialiasing); self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.scene().selectionChanged.connect(self.selection_changed)
        self.scale(20,20); self.centerOn(15,-7); self.rebuild()

    def selection_changed(self):
        items=[i for i in self.scene().selectedItems() if isinstance(i,ProfilePointItem)]
        self.point_selected.emit(items[0].vertex.id if items else '')

    def rebuild(self,selected=None):
        self.point_items={}; self.scene().clear()
        self.path_item=QGraphicsPathItem(); self.path_item.setPen(QPen(QColor('#23465c'),0))
        self.path_item.setAcceptedMouseButtons(Qt.NoButton); self.scene().addItem(self.path_item)
        self.mirror_item=QGraphicsPathItem(); self.mirror_item.setPen(QPen(QColor('#849eac'),0,Qt.DashLine))
        self.mirror_item.setAcceptedMouseButtons(Qt.NoButton); self.scene().addItem(self.mirror_item)
        for vertex in self.profile.vertices:
            item=ProfilePointItem(vertex,self); self.point_items[vertex.id]=item; self.scene().addItem(item)
            item.setSelected(vertex.id==selected)
        self.refresh_path(); self.draw_interfaces()

    def refresh_path(self):
        self.path_item.setPath(profile_path(self.profile))
        self.mirror_item.setPath(profile_path(self.profile,True) if self.mirrored else QPainterPath())

    def draw_interfaces(self):
        for interface in self.interfaces:
            z,r=interface.z_mm,interface.r_mm or 0
            marker=self.scene().addPolygon(QPolygonF([QPointF(z,-r-.3),QPointF(z+.3,-r),QPointF(z,-r+.3),QPointF(z-.3,-r)]),
                                          QPen(QColor('#b26a20'),0),QColor('#ffc66b'))
            marker.setZValue(4); marker.setAcceptedMouseButtons(Qt.NoButton)
            text=self.scene().addSimpleText(f'{interface.hydraulic_port_id} ({interface.interface_type})')
            text.setFlag(QGraphicsItem.ItemIgnoresTransformations); text.setPos(z+.5,-r-.5)
            text.setBrush(QColor('#8b4f15')); text.setAcceptedMouseButtons(Qt.NoButton)

    def mousePressEvent(self,event):
        pos=self.mapToScene(event.position().toPoint())
        if event.button()==Qt.MiddleButton:
            self.pan_start=event.position().toPoint(); self.setCursor(Qt.ClosedHandCursor); event.accept(); return
        if event.button()==Qt.LeftButton:
            if self.marker_mode:
                z,r=snapped(pos.x(),-pos.y(),self.snap_increment)
                self.marker_mode=False; self.marker_requested.emit(z,r); event.accept(); return
            hit=next((i for i in self.items(event.position().toPoint()) if isinstance(i,ProfilePointItem)),None)
            if not hit and self.add_mode:
                z,r=snapped(pos.x(),-pos.y(),self.snap_increment)
                try: vertex=self.profile.add_point(z,r,self.insert_after)
                except ValueError as error: self.message.emit(str(error)); return
                self.insert_after=None; self.rebuild(vertex.id); self.profile_changed.emit(); event.accept(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.pan_start is not None:
            pos=event.position().toPoint(); delta=pos-self.pan_start; self.pan_start=pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value()-delta.y())
            event.accept()
        else: super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MiddleButton:
            self.pan_start=None; self.unsetCursor(); event.accept()
        else: super().mouseReleaseEvent(event)

    def wheelEvent(self,event):
        factor=1.15 if event.angleDelta().y()>0 else 1/1.15
        if 2<=self.transform().m11()*factor<=400: self.scale(factor,factor)
        event.accept()

    def drawBackground(self,painter,rect):
        painter.fillRect(rect,QColor('#f4f7fa'))
        # Limit grid density to visible display detail.
        scale=self.transform().m11(); step=1 if scale>=12 else 5
        painter.setPen(QPen(QColor('#dce5ec'),0))
        z=math.floor(rect.left()/step)*step
        while z<=rect.right(): painter.drawLine(QPointF(z,rect.top()),QPointF(z,rect.bottom())); z+=step
        r=math.floor(rect.top()/step)*step
        while r<=rect.bottom(): painter.drawLine(QPointF(rect.left(),r),QPointF(rect.right(),r)); r+=step
        painter.setPen(QPen(QColor('#496478'),0,Qt.DashLine))
        painter.drawLine(QPointF(rect.left(),0),QPointF(rect.right(),0))
        painter.drawLine(QPointF(0,rect.top()),QPointF(0,rect.bottom()))
        # Labels drawn in viewport pixels stay readable at all zoom levels.
        painter.save(); painter.resetTransform(); painter.setPen(QColor('#304c61'))
        axis_y=self.mapFromScene(QPointF(0,0)).y(); datum_x=self.mapFromScene(QPointF(0,0)).x()
        y=max(20,min(self.viewport().height()-10,axis_y-8))
        painter.drawText(10,y,'R=0 revolve axis; Z → depth [mm]')
        x=max(10,min(self.viewport().width()-180,datum_x+8))
        painter.drawText(x,20,'Z=0 mounting face; R ↑ [mm]'); painter.restore()

    def fit_profile(self):
        points=[(v.z,v.r) for v in self.profile.vertices]+[(i.z_mm,i.r_mm or 0) for i in self.interfaces]
        if not points: return
        zs=[p[0] for p in points]+[0]; rs=[p[1] for p in points]+[0]
        rect=QRectF(min(zs),-max(rs),max(zs)-min(zs),max(rs)-min(rs))
        if self.mirrored: rect.setBottom(max(rs))
        self.fitInView(rect.adjusted(-2,-2,6,2),Qt.KeepAspectRatio)
        if self.transform().m11()>80:
            self.resetTransform(); self.scale(80,80); self.centerOn(rect.center())
