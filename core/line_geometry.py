"""Editable 2D line geometry, separate from hydraulic connectivity."""
import math
from core.geometry import SIDE_VECTORS, LEAD_LENGTH, rotated_side, wire_points


def local_port_positions(definition):
    from core.symbol_layout import symbol_dimensions
    w,h = symbol_dimensions(definition)
    if definition.symbol.get('kind') == 'external':
        p=definition.ports[0]; vx,vy=SIDE_VECTORS[p.side]
        return {p.id:(vx*w/2,vy*h/2)}
    result={}
    for side in SIDE_VECTORS:
        ports=[p for p in definition.ports if p.side==side]
        for index,p in enumerate(ports):
            fraction=(index+1)/(len(ports)+1)-.5
            result[p.id]=(-w/2 if side=='LEFT' else w/2,h*fraction) if side in ('LEFT','RIGHT') else (w*fraction,-h/2 if side=='TOP' else h/2)
    return result


def endpoint(project,node_id):
    node=project.nodes[node_id]; instance=project.instances[node.instance_id]
    definition=project.effective_definition(instance.id)
    port=next(p for p in definition.ports if p.id==node.port_id)
    x,y=local_port_positions(definition)[port.id]
    x,y=[(x,y),(-y,x),(-x,-y),(y,-x)][int(instance.rotation)//90]
    return (x+instance.x,y+instance.y),rotated_side(port.side,instance.rotation)


def normalize(points):
    result=[]
    for point in points:
        if not isinstance(point,(list,tuple)) or len(point)!=2 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in point):
            raise ValueError('Line geometry needs finite [x, y] points')
        point=list(point)
        if result and point==result[-1]: continue
        if result and point[0]!=result[-1][0] and point[1]!=result[-1][1]:
            result.append([point[0],result[-1][1]])
        result.append(point)
    return result


def lead_connector(lead,side,anchor):
    vx,vy=SIDE_VECTORS[side]
    if lead[0]==anchor[0] or lead[1]==anchor[1]:
        if (anchor[0]-lead[0])*vx+(anchor[1]-lead[1])*vy>=0: return [lead,anchor]
        if vx:
            y=lead[1]-LEAD_LENGTH
            return [lead,(lead[0],y),(anchor[0],y),anchor]
        x=lead[0]-LEAD_LENGTH
        return [lead,(x,lead[1]),(x,anchor[1]),anchor]
    corner=(lead[0],anchor[1]) if vx else (anchor[0],lead[1])
    return [lead,corner,anchor]


def routed_geometry(a,a_side,b,b_side,controls=()):
    controls=normalize(controls)
    if not controls:
        points=wire_points(a,a_side,b,b_side)
    else:
        av,bv=SIDE_VECTORS[a_side],SIDE_VECTORS[b_side]
        al=(a[0]+av[0]*LEAD_LENGTH,a[1]+av[1]*LEAD_LENGTH)
        bl=(b[0]+bv[0]*LEAD_LENGTH,b[1]+bv[1]*LEAD_LENGTH)
        points=[a,*lead_connector(al,a_side,controls[0]),*controls[1:],
                *reversed(lead_connector(bl,b_side,controls[-1])),b]
    return {'points':normalize(points),'controls':controls}


def validate_geometry(geometry):
    if not isinstance(geometry,dict) or set(geometry)!={'points','controls'}:
        raise ValueError('Invalid schematic line geometry')
    points=geometry['points']; controls=geometry['controls']
    if not isinstance(points,list) or len(points)<2 or not isinstance(controls,list):
        raise ValueError('Invalid schematic line geometry')
    if normalize(points)!=points or normalize(controls)!=controls:
        raise ValueError('Line geometry must be orthogonal with no duplicate adjacent points')


def crossing_points(lines):
    """Assign each strict interior crossing to the lexically larger line ID.

    Returns segment index -> crossing coordinates for the receiving line.
    Coincident/parallel segments, bends, and endpoints never become crossings.
    """
    result={key:{} for key in lines}
    keys=sorted(lines)
    for index,a_id in enumerate(keys):
        for b_id in keys[index+1:]:
            for ai,(a,b) in enumerate(zip(lines[a_id],lines[a_id][1:])):
                for bi,(c,d) in enumerate(zip(lines[b_id],lines[b_id][1:])):
                    ah=a[1]==b[1]; bh=c[1]==d[1]
                    if ah==bh: continue
                    h1,h2,v1,v2=(a,b,c,d) if ah else (c,d,a,b)
                    x,y=v1[0],h1[1]
                    if min(h1[0],h2[0])<x<max(h1[0],h2[0]) and min(v1[1],v2[1])<y<max(v1[1],v2[1]):
                        points=result[b_id].setdefault(bi,[])
                        if [x,y] not in points: points.append([x,y])
    return result
