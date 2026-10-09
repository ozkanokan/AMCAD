"""Deterministic shared symbol sizing for endpoint routing and rendering."""
def symbol_dimensions(definition):
    w,h=definition.symbol.get('width',110),definition.symbol.get('height',76)
    if definition.symbol.get('kind','box')!='box':return w,h
    groups={side:[p for p in definition.ports if p.side==side] for side in ('LEFT','RIGHT','TOP','BOTTOM')}
    text=lambda value: max(12,len(value)*12)
    left=max((text(p.display_name) for p in groups['LEFT']),default=0)
    right=max((text(p.display_name) for p in groups['RIGHT']),default=0)
    w=max(w,text(definition.name)+32,left+right+text(definition.name)+48)
    for side in ('TOP','BOTTOM'):
        labels=groups[side]
        w=max(w,(max((text(p.display_name) for p in labels),default=0)+24)*(len(labels)+1))
    h=max(h,36*(max(len(groups['LEFT']),len(groups['RIGHT']))+1),100 if groups['TOP'] or groups['BOTTOM'] else 76)
    return w,h
