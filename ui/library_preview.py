"""Thumbnails rendered from actual stored symbol/profile geometry."""
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QPixmap,QPainter,QIcon,QPen,QColor
from PySide6.QtWidgets import QGraphicsScene,QGraphicsSimpleTextItem


def render_scene(scene):
    pixmap=QPixmap(120,80);pixmap.fill(Qt.transparent)
    painter=QPainter(pixmap);painter.setRenderHint(QPainter.Antialiasing)
    bounds=None
    for item in scene.items():
        if item.isVisible():bounds=item.sceneBoundingRect() if bounds is None else bounds.united(item.sceneBoundingRect())
    bounds=bounds or QRectF()
    margin=max(bounds.width(),bounds.height(),.01)*.06
    bounds=bounds.adjusted(-margin,-margin,margin,margin)
    if not bounds.isEmpty():scene.render(painter,QRectF(0,0,120,80),bounds,Qt.KeepAspectRatio)
    painter.end();return QIcon(pixmap)


def component_icon(definition):
    from core.project import Project
    from ui.component_item import ComponentItem
    class Canvas:
        def __init__(self):self.project=Project()
    canvas=Canvas();instance=canvas.project.add_instance(definition)
    scene=QGraphicsScene();item=ComponentItem(instance,definition,canvas);item.label.hide();item.preview_symbol=True
    for child in item.childItems():
        if isinstance(child,QGraphicsSimpleTextItem):child.hide()
    for port in item.ports.values():
        pen=QPen(QColor('#17657a'),1.2);pen.setCosmetic(True);port.setPen(pen)
    scene.addItem(item)
    return render_scene(scene)


def cavity_icon(cavity):
    from ui.cavity_sketch_view import profile_path
    scene=QGraphicsScene()
    try:scene.addPath(profile_path(cavity.profile),QPen(QColor('#236477'),0))
    except ValueError:return QIcon()
    return render_scene(scene)
