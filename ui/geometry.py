from PySide6.QtCore import QPointF


def port_positions(definition):
    kind = definition.symbol.get('kind', 'box')
    if kind in {'junction', 'external'}:
        return {definition.ports[0].id: QPointF(0, 0)}
    w = definition.symbol.get('width', 110)
    h = definition.symbol.get('height', 76)
    positions = {}
    for side in ('LEFT', 'RIGHT', 'TOP', 'BOTTOM'):
        ports = [p for p in definition.ports if p.side == side]
        for index, p in enumerate(ports):
            fraction = (index + 1) / (len(ports) + 1)
            if side in ('LEFT', 'RIGHT'):
                positions[p.id] = QPointF(-w/2 if side == 'LEFT' else w/2, h*(fraction-.5))
            else:
                positions[p.id] = QPointF(w*(fraction-.5), -h/2 if side == 'TOP' else h/2)
    return positions
