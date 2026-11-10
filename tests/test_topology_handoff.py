"""Regression coverage for topology work recovered from the local source ZIP."""
from copy import deepcopy
import json
import pytest
from integrations.grasshopper.topology_core import Topology, Draft, make_port, bind_port
from integrations.grasshopper import topology_overview, topology_diagnostics


def model():
    ports = [make_port('cavity', name, [x, 0, 0], [0, 0, 1],
                       {'type': 'CIRCLE', 'diameter_mm': 2})
             for name, x in [('A', 0), ('B', 10), ('C', 20)]]
    graph = {'nodes': [], 'nets': [{'id': 'existing-route', 'terminals': [
        {'instance_id': p['instance_id'], 'interface_id': p['id']}
        for p in ports[:2]]}]}
    return Topology(ports, graph)


def test_endpoint_edit_retains_route_and_rolls_back_invalid_edit():
    m = model(); refs = list(m.base); source = deepcopy(m.source_graph)
    m.edit_group('existing-route', [refs[0], refs[2]])
    before = deepcopy(m.doc)
    with pytest.raises(ValueError):
        m.edit_group('existing-route', [refs[0], refs[0]])
    assert m.doc == before
    metadata, graph = m.outputs()
    assert json.loads(graph)['nets'][0]['id'] == 'existing-route'
    assert m.source_graph == source and len(metadata) == 3


def test_bound_extra_port_follows_host_and_overview_renders():
    m = model(); host = m.original[0]
    extra = make_port('cavity', 'Extra', [0, 5, 0], [0, 0, 1],
                      {'type': 'CIRCLE', 'diameter_mm': 1})
    ref = m.add_port(bind_port(extra, host))
    moved = deepcopy(m.original)
    moved[0]['position_mm'][0] += 100
    restored = Topology(moved, m.source_graph, m.doc)
    assert restored.all_ports()[ref]['position_mm'] == [100, 5, 0]
    assert 'Extra' in topology_overview.svg(restored)


def test_draft_save_isolated_and_refuses_to_overwrite_project(tmp_path):
    m = model(); path = tmp_path / 'topology.json'; published = []
    state = dict(model=m, metadata=m.original, connectivity=m.source_graph, path=str(path))
    draft = Draft(state, lambda: published.append(True))
    draft.model.delete_group('existing-route')
    assert state['model'].doc['groups'] and not path.exists()
    draft.publish()
    assert published == [True] and not state['model'].doc['groups']
    assert topology_diagnostics.inspect_sidecar(path)['schema'] == 1
    path.write_text('{"schema": "amcad.project", "sentinel": true}')
    before = path.read_bytes()
    with pytest.raises(ValueError):
        draft.model.save(str(path))
    assert path.read_bytes() == before
