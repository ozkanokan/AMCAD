"""Read-only automatic SVG overview and stable-ID labels. No UI or CAD dependencies."""
from html import escape


def catalog(model):
    names={};instances={}
    for node in model.source_graph.get('nodes',[]):
        terminal=node.get('physical_terminal')
        if not terminal:continue
        ref=(str(terminal['instance_id']),str(terminal['interface_id']))
        full=str(node.get('name') or '')
        if full:
            parts=full.rsplit('.',1);instances[ref[0]]=parts[0]
            if len(parts)==2:names[ref]=parts[1]
    disabled={tuple(r) for r in model.doc['disabled']}
    used={tuple(ref):g['id'] for g in model.doc['groups'] for ref in g['ports']}
    result=[]
    for ref,port in model.all_ports().items():
        instance=instances.get(ref[0]) or port.get('instance_name') or 'Cavity '+ref[0][:8]
        name=names.get(ref) or port.get('label') or ref[1][:12]
        result.append({'ref':ref,'instance_name':instance,'port_name':name,'label':instance+' / '+name,
                       'enabled':ref not in disabled,'group_id':used.get(ref)})
    return sorted(result,key=lambda r:(r['instance_name'].casefold(),r['ref'][0],r['port_name'].casefold(),r['ref'][1]))


def connections(model):
    labels={r['ref']:r['label'] for r in catalog(model)}
    result=[]
    for g in model.doc['groups']:
        kind='PAIR' if len(g['ports'])==2 else 'Y3'
        ends=[labels[tuple(ref)] for ref in g['ports']]
        text=('  ↔  '.join(ends)) if kind=='PAIR' else ('junction joining '+'  +  '.join(ends))
        result.append({'id':g['id'],'kind':kind,'text':kind+' | '+text,'ports':[tuple(r) for r in g['ports']]})
    return result


def svg(model,selected=None):
    """One rectangle per cavity; ports are distinct endpoints; Y3 is one 3-arm node.

    Layout is regenerated from IDs/names on every draft change. Saved canvas
    layout is deliberately ignored and retained unmodified for v1 compatibility.
    """
    records=catalog(model);by_instance={}
    for r in records:by_instance.setdefault(r['ref'][0],[]).append(r)
    blocks=[];positions={};y=45
    for iid,ports in by_instance.items():
        height=46+24*len(ports);blocks.append((iid,ports,20,y,280,height))
        for index,r in enumerate(ports):positions[r['ref']]=(300,y+45+24*index)
        y+=height+30
    groups=model.doc['groups'];width=max(600,400+len(groups)*55);height=max(140,y)
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" viewBox="0 0 {} {}" role="img" aria-label="Physical port connection overview">'.format(width,height,width,height),
           '<rect width="100%" height="100%" fill="#ffffff"/>',
           '<text x="20" y="22" font-family="Arial,sans-serif" font-size="14" fill="#17212b">{} cavities | {} physical ports | {} PAIR/Y3 connections</text>'.format(len(blocks),len(records),len(groups))]
    for number,g in enumerate(groups):
        points=[positions[tuple(r)] for r in g['ports']];track=360+55*number
        color='#d47700' if g['id']==selected else '#1767ac'
        parts.append('<g data-connection="{}" stroke="{}" stroke-width="2" fill="none">'.format(escape(g['id'],quote=True),color))
        if len(points)==2:
            a,b=points;parts.append('<path data-kind="PAIR" d="M {} {} H {} V {} H {}"/>'.format(a[0],a[1],track,b[1],b[0]))
        else:
            jy=sum(p[1] for p in points)/3
            for x,py in points:parts.append('<line data-kind="Y3_BRANCH" x1="{}" y1="{}" x2="{}" y2="{}"/>'.format(x,py,track,jy))
            parts.append('<circle data-kind="Y3_JUNCTION" cx="{}" cy="{}" r="5" fill="{}"/>'.format(track,jy,color))
            parts.append('<text x="{}" y="{}" stroke="none" fill="{}" font-family="Arial,sans-serif" font-size="12">Y3</text>'.format(track+8,jy-7,color))
        parts.append('<title>{}</title></g>'.format(escape(g['id'])))
    for iid,ports,x,y,w,h in blocks:
        parts.append('<g data-cavity="{}"><rect x="{}" y="{}" width="{}" height="{}" rx="3" fill="#eef3f8" stroke="#52677b"/>'.format(escape(iid,quote=True),x,y,w,h))
        name=ports[0]['instance_name']
        parts.append('<text x="{}" y="{}" font-family="Arial,sans-serif" font-size="14" font-weight="bold" fill="#17212b">{}<title>{}</title></text>'.format(x+10,y+23,escape(name[:32]),escape(name)))
        for r in ports:
            px,py=positions[r['ref']];color='#999999' if not r['enabled'] else '#248442' if r['group_id'] else '#ffffff'
            parts.append('<circle data-port="{}" cx="{}" cy="{}" r="4" fill="{}" stroke="#52677b"/>'.format(escape(r['ref'][1],quote=True),px,py,color))
            name=r['port_name'];suffix=' (disabled)' if not r['enabled'] else ''
            parts.append('<text x="{}" y="{}" text-anchor="end" font-family="Arial,sans-serif" font-size="12" fill="#17212b">{}{}<title>{}</title></text>'.format(px-10,py+4,escape(name[:30]),suffix,escape(r['label'])))
        parts.append('</g>')
    if not records:parts.append('<text x="20" y="70" font-family="Arial,sans-serif" font-size="14">No physical ports in the input metadata.</text>')
    parts.append('</svg>');return '\n'.join(parts)


def document(model,selected=None):
    return ('<!doctype html><html><head><meta charset="utf-8"/>'
            '<meta http-equiv="X-UA-Compatible" content="IE=edge"/>'
            '<style>body{margin:0;background:white;}svg{display:block;max-width:100%;height:auto;}</style>'
            '</head><body>'+svg(model,selected)+'</body></html>')
