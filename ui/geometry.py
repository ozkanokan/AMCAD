from PySide6.QtCore import QPointF
from core.line_geometry import local_port_positions


def port_positions(definition):
    return {key:QPointF(*point) for key,point in local_port_positions(definition).items()}
