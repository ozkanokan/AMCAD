"""AMCAD v2e: compact two-pane Eto editor; no Drawable."""
import copy
import traceback
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
from System.Drawing import Color
import Eto.Forms as ef
import Eto.Drawing as ed
from System import Array, String
from topology_core import Topology


def ctrl(kind, text):
    c = kind()
    c.Text = str(text)
    return c


def vector3(value):
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            return [float(v) for v in value]
        except (TypeError, ValueError):
            return None
    return None


def location(port):
    for field in ('position_mm', 'world_position_mm', 'position', 'origin_mm', 'stub_endpoint'):
        coords = vector3(port.get(field))
        if coords is not None:
            return rg.Point3d(*coords)
    return None


class PortHighlight(rd.DisplayConduit):
    def __init__(self):
        super().__init__()
        self.point = None
        self.direction = None
        self.label = ''
        self.terminals = []
        self.cavity_ports = []

    def DrawForeground(self, e):
        for pt, name in self.cavity_ports:
            e.Display.DrawDot(pt, name, Color.White, Color.DimGray)
        for pt, name in self.terminals:
            e.Display.DrawDot(pt, name, Color.Black, Color.DeepSkyBlue)
        if self.point is None:
            return
        e.Display.DrawDot(self.point, self.label, Color.Black, Color.Yellow)
        if self.direction is not None:
            e.Display.DrawArrow(rg.Line(self.point, self.point + self.direction * 6.0),
                                Color.OrangeRed, 2, 0.8)


def redraw():
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is not None:
        doc.Views.Redraw()


class TopologyEditor(ef.Form):
    def __init__(self, state, request_solution):
        super().__init__()
        self.state = state
        self.request_solution = request_solution
        self.draft = self.make_draft()
        self.selected = []
        self.port_refs = []
        self.group_ids = []
        self._refreshing = False
        self.highlight = None
        self.names = {}
        self.instance_names = {}
        self.active_selection = 'port'
        self.build_names()
        self.Title = 'AMCAD | Cavity Topology Editor v2e'
        self.ClientSize = ed.Size(1040, 610)
        self.MinimumSize = ed.Size(830, 490)
        self.Resizable = True

        self.ports = ef.ListBox()
        self.groups = ef.ListBox()
        self.picks = ef.ListBox()
        self.status = ctrl(ef.Label, 'Select a port to inspect; Add places it in the connection draft.')
        self.ports.Height = 370
        self.groups.Height = 270
        self.picks.Height = 90
        self.ports.SelectedIndexChanged += self.port_changed
        self.groups.SelectedIndexChanged += self.group_changed
        self.highlight_checkbox = ef.CheckBox()
        self.highlight_checkbox.Text = 'Rhino highlight'
        self.highlight_checkbox.Checked = True
        self.highlight_checkbox.CheckedChanged += self.highlight_changed

        add = ctrl(ef.Button, '+ Add port')
        remove = ctrl(ef.Button, '- Last')
        clear = ctrl(ef.Button, 'Clear')
        pair = ctrl(ef.Button, '+ PAIR')
        y3 = ctrl(ef.Button, '+ Y3')
        delete = ctrl(ef.Button, 'Delete route')
        disable = ctrl(ef.Button, 'Enable / Disable')
        save = ctrl(ef.Button, 'Save + Apply to GH')
        discard = ctrl(ef.Button, 'Discard draft')
        close = ctrl(ef.Button, 'Close')
        add.Click += lambda sender, e: self.add_pick()
        remove.Click += lambda sender, e: self.remove_pick()
        clear.Click += lambda sender, e: self.clear_picks()
        pair.Click += lambda sender, e: self.create_group(2)
        y3.Click += lambda sender, e: self.create_group(3)
        delete.Click += lambda sender, e: self.delete_group()
        disable.Click += lambda sender, e: self.toggle_port()
        save.Click += lambda sender, e: self.save()
        discard.Click += lambda sender, e: self.discard()
        close.Click += lambda sender, e: self.Close()

        left = ef.DynamicLayout()
        left.Padding = ed.Padding(4)
        left.Spacing = ed.Size(5, 5)
        left.AddRow(ctrl(ef.Label, 'CAVITIES / PHYSICAL PORTS'))
        left.AddRow(self.ports)
        left.AddRow(add, disable)
        left.AddRow(self.highlight_checkbox)

        right = ef.DynamicLayout()
        right.Padding = ed.Padding(4)
        right.Spacing = ed.Size(5, 5)
        right.AddRow(ctrl(ef.Label, 'PHYSICAL CONNECTIONS  |  PAIR / Y3'))
        right.AddRow(self.groups)
        right.AddRow(pair, y3, delete)
        right.AddRow(ctrl(ef.Label, 'NEW CONNECTION  |  Selected terminals'))
        right.AddRow(self.picks)
        right.AddRow(remove, clear)

        layout = ef.DynamicLayout()
        layout.Padding = ed.Padding(9)
        layout.Spacing = ed.Size(7, 7)
        layout.AddRow(left, right)
        layout.AddRow(save, discard, close)
        layout.AddRow(self.status)
        self.Content = layout
        self.Closed += self.closed
        self.refresh()

    def build_names(self):
        # Labels are display-only; topology keys and routing IDs remain untouched.
        for node in self.state['connectivity'].get('nodes', []):
            term = node.get('physical_terminal')
            if isinstance(term, dict):
                ref = (str(term.get('instance_id', '')), str(term.get('interface_id', '')))
                self.names[ref] = str(node.get('name') or node.get('port_id') or '')
        for ref, p in self.draft.all_ports().items():
            for field in ('instance_name', 'cavity_name', 'component_name'):
                if p.get(field):
                    self.instance_names[ref[0]] = str(p[field]); break
            for field in ('port_name', 'interface_name', 'label', 'name'):
                if p.get(field) and ref not in self.names:
                    self.names[ref] = str(p[field]); break

    def label(self, ref):
        ref = tuple(ref)
        inst, port = ref
        cavity = self.instance_names.get(inst, 'Cavity ' + inst[:8])
        port_label = self.names.get(ref) or 'Port ' + port[:8]
        return '{} / {}'.format(cavity, port_label)

    def clear_highlight(self):
        if self.highlight is not None:
            self.highlight.Enabled = False
            self.highlight.point = None
            self.highlight.terminals = []
            self.highlight.cavity_ports = []
            self.highlight = None
            redraw()

    def highlight_changed(self, sender, event):
        if self.highlight_checkbox.Checked:
            self.update_highlight()
        else:
            self.clear_highlight()

    def port_changed(self, sender, event):
        if not self._refreshing:
            self.active_selection = 'port'
            if self.highlight_checkbox.Checked:
                self.update_highlight()

    def group_changed(self, sender, event):
        if not self._refreshing:
            self.active_selection = 'group'
            if self.highlight_checkbox.Checked:
                self.update_highlight()

    def update_highlight(self):
        try:
            ports = self.draft.all_ports()
            refs = []
            main = None
            if self.active_selection == 'group':
                i = self.groups.SelectedIndex
                if 0 <= i < len(self.group_ids):
                    refs = [tuple(x) for x in self.draft.doc['groups'][i]['ports']]
            else:
                i = self.ports.SelectedIndex
                main = self.selected_port()
                if main is not None:
                    refs = [main]
            if not refs:
                self.clear_highlight()
                return
            if self.highlight is None:
                self.highlight = PortHighlight()
            h = self.highlight
            h.point = None
            h.direction = None
            h.terminals = []
            h.cavity_ports = []
            for ref in refs:
                p = ports.get(ref)
                pt = location(p) if p else None
                if pt is not None:
                    h.terminals.append((pt, self.label(ref)))
            if main is not None:
                p = ports[main]
                h.point = location(p)
                h.label = self.label(main)
                for ref, other in ports.items():
                    if ref[0] == main[0] and ref != main:
                        pt = location(other)
                        if pt is not None:
                            h.cavity_ports.append((pt, self.names.get(ref, 'Port')))
                d = vector3(p.get('direction'))
                if d is not None:
                    v = rg.Vector3d(*d)
                    if v.Unitize():
                        h.direction = v
            if not h.terminals:
                self.clear_highlight()
                self.status.Text = 'No world-space coordinates for selected terminals.'
                return
            h.Enabled = True
            redraw()
            self.status.Text = 'Highlighted {} terminal(s) in Rhino.'.format(len(h.terminals))
        except Exception as exc:
            self.clear_highlight()
            self.status.Text = 'Highlight error: ' + str(exc)

    def make_draft(self):
        return Topology(self.state['metadata'], self.state['connectivity'],
                        copy.deepcopy(self.state['model'].doc))

    def refresh(self):
        self._refreshing = True
        try:
            # The header rows are display-only; real port keys remain unchanged.
            previous_port = None
            if hasattr(self, 'port_rows'):
                i = self.ports.SelectedIndex
                if 0 <= i < len(self.port_rows):
                    previous_port = self.port_rows[i]
            previous_group = None
            if self.group_ids:
                i = self.groups.SelectedIndex
                if 0 <= i < len(self.group_ids):
                    previous_group = self.group_ids[i]
            self.port_refs = sorted(self.draft.all_ports())
            disabled = {tuple(x) for x in self.draft.doc['disabled']}
            by_inst = {}
            for ref in self.port_refs:
                by_inst.setdefault(ref[0], []).append(ref)
            self.port_rows = []
            display = []
            for inst in sorted(by_inst, key=lambda x: self.instance_names.get(x, x)):
                name = self.instance_names.get(inst, 'Cavity ' + inst[:8])
                refs = by_inst[inst]
                display.append('▾  {}   ({} ports)'.format(name, len(refs)))
                self.port_rows.append(None)
                for ref in sorted(refs, key=lambda r: self.names.get(r, r[1])):
                    pname = self.names.get(ref) or 'Port ' + ref[1][:8]
                    display.append('    {}   {}'.format('○' if ref in disabled else '●', pname))
                    self.port_rows.append(ref)
            self.ports.DataStore = Array[String](display)
            self.group_ids = [g['id'] for g in self.draft.doc['groups']]
            self.groups.DataStore = Array[String]([
                '{}  |  {}'.format('Y3' if len(g['ports']) == 3 else 'PAIR',
                  '  →  '.join(self.names.get(tuple(r), tuple(r)[1][:8]) for r in g['ports']))
                for g in self.draft.doc['groups']])
            self.picks.DataStore = Array[String]([self.label(r) for r in self.selected])
            if previous_port in self.port_rows and previous_port is not None:
                self.ports.SelectedIndex = self.port_rows.index(previous_port)
            if previous_group in self.group_ids:
                self.groups.SelectedIndex = self.group_ids.index(previous_group)
        finally:
            self._refreshing = False

    def selected_port(self):
        i = self.ports.SelectedIndex
        if hasattr(self, 'port_rows') and 0 <= i < len(self.port_rows):
            return self.port_rows[i]
        return None

    def add_pick(self):
        ref = self.selected_port()
        if ref is None:
            self.status.Text = 'Select a port (not a cavity heading). '
            return
        if ref in self.selected:
            self.status.Text = 'Port already selected.'
        elif len(self.selected) >= 3:
            self.status.Text = 'Maximum 3 ports per group.'
        else:
            self.selected.append(ref)
            self.refresh()
            self.status.Text = '{} selected terminal(s).'.format(len(self.selected))

    def remove_pick(self):
        if self.selected:
            self.selected.pop()
            self.refresh()

    def clear_picks(self):
        self.selected = []
        self.refresh()

    def mutate(self, action):
        before = copy.deepcopy(self.draft.doc)
        try:
            action()
            self.draft.validate()
            self.refresh()
            self.status.Text = 'UNSAVED DRAFT. Save to apply to GH.'
            return True
        except Exception as exc:
            self.draft.doc = before
            self.refresh()
            self.status.Text = 'ERROR: ' + str(exc)
            return False

    def create_group(self, n):
        if len(self.selected) != n:
            self.status.Text = 'Select exactly {} ports.'.format(n)
            return
        refs = list(self.selected)
        if self.mutate(lambda: self.draft.add_group(refs)):
            self.selected = []
            self.refresh()

    def delete_group(self):
        i = self.groups.SelectedIndex
        if not 0 <= i < len(self.group_ids):
            self.status.Text = 'Select a connection first.'
            return
        gid = self.group_ids[i]
        self.mutate(lambda: self.draft.delete_group(gid))

    def toggle_port(self):
        ref = self.selected_port()
        if ref is None:
            self.status.Text = 'Select a port (not a cavity heading). '
            return
        disabled = {tuple(x) for x in self.draft.doc['disabled']}
        self.mutate(lambda: self.draft.set_disabled(ref, ref not in disabled))

    def save(self):
        try:
            self.draft.validate()
            # Persist first; do not publish to GH if writing fails.
            self.draft.save(self.state['path'])
            self.state['model'] = self.make_draft_from_doc()
            self.status.Text = 'SAVED. GH solution scheduled.'
            self.request_solution()
        except Exception as exc:
            self.status.Text = 'SAVE ERROR: ' + str(exc)

    def make_draft_from_doc(self):
        return Topology(self.state['metadata'], self.state['connectivity'],
                        copy.deepcopy(self.draft.doc))

    def discard(self):
        self.draft = self.make_draft()
        self.selected = []
        self.refresh()
        self.clear_highlight()
        self.status.Text = 'Draft discarded; GH topology unchanged.'

    def closed(self, sender, event):
        self.clear_highlight()
        if self.state.get('window') is self:
            self.state['window'] = None
