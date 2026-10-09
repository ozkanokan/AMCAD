"""Qt software-rendered orthographic/ISO preview, including parametric mesh picking."""
from copy import deepcopy
import math
from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QPolygonF, QPalette, QQuaternion, QVector3D
from PySide6.QtWidgets import QWidget
from core.cavity_surface import dot, sub, cross, normalized, interface_pose, channel_mesh


def barycentric(point,a,b,c):
    denominator=(b.y()-c.y())*(a.x()-c.x())+(c.x()-b.x())*(a.y()-c.y())
    if abs(denominator)<1e-8: return None
    u=((b.y()-c.y())*(point.x()-c.x())+(c.x()-b.x())*(point.y()-c.y()))/denominator
    v=((c.y()-a.y())*(point.x()-c.x())+(a.x()-c.x())*(point.y()-c.y()))/denominator
    w=1-u-v
    return (u,v,w) if min(u,v,w)>=-1e-7 else None


class CavitySurfaceView(QWidget):
    anchor_requested=Signal(object)
    port_selected=Signal(str)
    port_edit_requested=Signal(str)
    escape_requested=Signal()

    def __init__(self,label,parent=None):
        super().__init__(parent)
        self.label=label; self.profile=None; self.surface=None; self.interfaces=[]; self.channels={}
        self.selected_port=None; self.place_mode=False
        a,e=math.radians(-35),math.radians(30)
        right=(math.cos(a),-math.sin(a),0)
        up=(math.sin(a)*math.sin(e),math.cos(a)*math.sin(e),math.cos(e))
        self.orientation=QQuaternion.fromAxes(QVector3D(*right),QVector3D(*up),QVector3D(*cross(right,up)))
        self.camera_axes=(right,up,cross(right,up))
        self.zoom=12; self.pan=QPointF(); self.center=(0,0,0); self.last_mouse=None; self.mouse_button=None
        self.setMinimumSize(200,170); self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip('Left drag: orbit (ISO); middle/right drag: pan; wheel: zoom; double-click port: edit')

    def basis(self):
        if self.label=='XZ': return (0,0,1),(1,0,0),(0,1,0)
        if self.label=='XY': return (1,0,0),(0,1,0),(0,0,1)
        return self.camera_axes

    def trackball(self,position):
        """Continuous virtual sphere in camera coordinates, centered on the view target."""
        scale=max(1,min(self.width(),self.height())/2)
        x=(position.x()-self.width()/2-self.pan.x())/scale
        y=(self.height()/2+self.pan.y()-position.y())/scale
        length=math.hypot(x,y)
        if length>1: return QVector3D(x/length,y/length,0)
        return QVector3D(x,y,math.sqrt(max(0,1-x*x-y*y)))

    def orbit(self,start,end):
        rotation=QQuaternion.rotationTo(self.trackball(start),self.trackball(end))
        self.orientation=(self.orientation*rotation.conjugated()).normalized()
        axes=[self.orientation.rotatedVector(axis) for axis in (QVector3D(1,0,0),QVector3D(0,1,0),QVector3D(0,0,1))]
        self.camera_axes=tuple(v.toTuple() for v in axes)

    def project(self,xyz):
        right,up,depth=self.basis(); relative=sub(xyz,self.center)
        return QPointF(self.width()/2+self.pan.x()+self.zoom*dot(relative,right),
                       self.height()/2+self.pan.y()-self.zoom*dot(relative,up)),dot(relative,depth)

    def set_geometry(self,profile,surface,interfaces,selected=None):
        first=self.surface is None or not self.surface.vertices
        self.profile=profile; self.surface=surface; self.interfaces=interfaces; self.selected_port=selected
        self.channels={}
        for interface in interfaces:
            try: self.channels[interface.id]=channel_mesh(profile,interface)
            except ValueError: pass  # Invalid anchor stays in the model/table, never relocated.
        if first and surface is not None: self.fit()
        self.update()

    def fit(self):
        vertices=[] if self.surface is None else list(self.surface.vertices)
        for mesh in self.channels.values(): vertices.extend(mesh.vertices)
        if not vertices: return
        self.center=tuple((min(v[k] for v in vertices)+max(v[k] for v in vertices))/2 for k in range(3))
        right,up,_=self.basis()
        xs=[dot(sub(v,self.center),right) for v in vertices]; ys=[dot(sub(v,self.center),up) for v in vertices]
        self.zoom=max(.1,min((self.width()-60)/max(max(xs)-min(xs),1),(self.height()-60)/max(max(ys)-min(ys),1)))
        self.pan=QPointF(); self.update()

    def projected(self,mesh): return [self.project(v) for v in mesh.vertices]

    def pick_surface(self,position):
        if self.surface is None: return None
        projected=self.projected(self.surface); best=None
        for index,triangle in enumerate(self.surface.triangles):
            weights=barycentric(position,*(projected[i][0] for i in triangle))
            if weights is None: continue
            depth=sum(w*projected[i][1] for w,i in zip(weights,triangle))
            if best is None or depth>best[0]:
                base,parameters=self.surface.anchors[index]
                anchor=deepcopy(base)
                anchor.t=max(0,min(1,sum(w*p[0] for w,p in zip(weights,parameters))))
                anchor.angle_deg=sum(w*p[1] for w,p in zip(weights,parameters))%360
                best=(depth,anchor)
        return best[1] if best else None

    def pick_port(self,position):
        # Anchor handles are usable even when channels overlap in projection.
        handles=[]
        for interface in self.interfaces:
            try: p,_=self.project(interface_pose(self.profile,interface)[0])
            except ValueError: continue
            distance=math.hypot(p.x()-position.x(),p.y()-position.y())
            if distance<=10: handles.append((distance,interface.id))
        if handles: return min(handles)[1]
        best=None
        for interface_id,mesh in self.channels.items():
            projected=self.projected(mesh)
            for triangle in mesh.triangles:
                weights=barycentric(position,*(projected[i][0] for i in triangle))
                if weights is None: continue
                depth=sum(w*projected[i][1] for w,i in zip(weights,triangle))
                if best is None or depth>best[0]: best=(depth,interface_id)
        return best[1] if best else None

    def paintEvent(self,event):
        painter=QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        dark=self.palette().color(QPalette.Base).lightness()<128
        background=QColor('#18232d' if dark else '#f4f7fa')
        foreground=QColor('#e7eef4' if dark else '#304c61')
        painter.fillRect(self.rect(),background)
        faces=[]
        meshes=[] if self.surface is None else [(None,self.surface)]
        meshes.extend(self.channels.items())
        for interface_id,mesh in meshes:
            projected=self.projected(mesh)
            for triangle in mesh.triangles:
                points=[projected[i][0] for i in triangle]
                if abs((points[1].x()-points[0].x())*(points[2].y()-points[0].y())-(points[1].y()-points[0].y())*(points[2].x()-points[0].x()))<.02: continue
                normal=cross(sub(mesh.vertices[triangle[1]],mesh.vertices[triangle[0]]),sub(mesh.vertices[triangle[2]],mesh.vertices[triangle[0]]))
                length=math.hypot(*normal)
                shade=.55+.45*abs(dot(tuple(v/length for v in normal),(0.3,.4,.866))) if length>1e-12 else .7
                if interface_id is None: color=QColor(int(60*shade),int(145*shade),int(195*shade),65)
                elif interface_id==self.selected_port: color=QColor(250,int(190*shade),45,220)
                else: color=QColor(int(220*shade),int(125*shade),int(48*shade),200)
                faces.append((sum(projected[i][1] for i in triangle)/3,QPolygonF(points),color))
        painter.setPen(Qt.NoPen)
        for _,polygon,color in sorted(faces,key=lambda f:f[0]):
            painter.setBrush(color); painter.drawPolygon(polygon)
        painter.setBrush(background)
        for interface in self.interfaces:
            try: p,_=self.project(interface_pose(self.profile,interface)[0])
            except ValueError: continue
            painter.setPen(QPen(QColor('#ffa828' if interface.id==self.selected_port else '#b27732'),2))
            painter.drawEllipse(p,4,4)
            painter.setPen(foreground); painter.drawText(p+QPointF(7,-6),interface.hydraulic_port_id)
        origin,_=self.project((0,0,0))
        for name,axis,color in [('X',(1,0,0),'#d66a68'),('Y',(0,1,0),'#53a271'),('Z',(0,0,1),'#578fd0')]:
            endpoint,_=self.project(tuple(3*v for v in axis))
            painter.setPen(QPen(QColor(color),1.5)); painter.drawLine(origin,endpoint); painter.drawText(endpoint+QPointF(3,-3),name)
        painter.setPen(foreground)
        painter.drawText(10,20,self.label+' • mm'+(' • Add Port: click surface' if self.place_mode else ''))
        if self.surface is None: painter.drawText(10,45,'No valid profile surface')
        if self.label=='ISO': painter.drawText(10,self.height()-10,'Drag: orbit • middle/right: pan • wheel: zoom')

    def mousePressEvent(self,event):
        self.setFocus()
        if event.button()==Qt.LeftButton:
            if self.place_mode:
                anchor=self.pick_surface(event.position())
                if anchor is not None: self.anchor_requested.emit(anchor)
                event.accept(); return
            selected=self.pick_port(event.position())
            if selected:
                self.port_selected.emit(selected); event.accept(); return
        self.last_mouse=event.position(); self.mouse_button=event.button(); event.accept()

    def mouseMoveEvent(self,event):
        if self.last_mouse is None: return
        previous=self.last_mouse
        delta=event.position()-previous; self.last_mouse=event.position()
        if self.mouse_button==Qt.LeftButton and self.label=='ISO':
            self.orbit(previous,event.position())
        else: self.pan+=delta
        self.update(); event.accept()

    def mouseReleaseEvent(self,event):
        self.last_mouse=None; self.mouse_button=None; event.accept()

    def mouseDoubleClickEvent(self,event):
        selected=self.pick_port(event.position())
        if selected and not self.place_mode: self.port_edit_requested.emit(selected)
        event.accept()

    def wheelEvent(self,event):
        previous=self.zoom
        self.zoom=max(.01,min(1000,self.zoom*(1.15 if event.angleDelta().y()>0 else 1/1.15)))
        offset=event.position()-QPointF(self.width()/2,self.height()/2)-self.pan
        self.pan-=offset*(self.zoom/previous-1)
        self.update(); event.accept()

    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Escape: self.escape_requested.emit(); event.accept()
        else: super().keyPressEvent(event)
