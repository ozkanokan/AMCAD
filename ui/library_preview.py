"""Thumbnails rendered from actual stored symbol/profile geometry."""
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QPixmap,QPainter,QIcon,QPen,QColor
from PySide6.QtWidgets import QGraphicsScene


def render_scene(scene):
    pixmap=QPixmap(120,80);pixmap.fill(Qt.transparent)
    painter=QPainter(pixmap);painter.setRenderHint(QPainter.Antialiasing)
    bounds=scene.itemsBoundingRect().adjusted(-8,-8,8,8)
    if not bounds.isEmpty():scene.render(painter,QRectF(0,0,120,80),bounds,Qt.KeepAspectRatio)
    painter.end();return QIcon(pixmap)


def component_icon(definition):
    from core.project import Project
    from ui.component_item import ComponentItem
    class Canvas:
        def __init__(self):self.project=Project()
    canvas=Canvas();instance=canvas.project.add_instance(definition)
    scene=QGraphicsScene();item=ComponentItem(instance,definition,canvas);item.label.hide();scene.addItem(item)
    return render_scene(scene)


def cavity_icon(cavity):
    from ui.cavity_sketch_view import profile_path
    scene=QGraphicsScene()
    try:scene.addPath(profile_path(cavity.profile),QPen(QColor('#236477'),1))
    except ValueError:return QIcon()
    return render_scene(scene)
