# V1.2 project and graph contracts

Formats are UTF-8 JSON with `schema` and integer `schema_version`. Current
version is **3**. Version 1/2 projects migrate explicitly on load. Graph exports
are output-only. Unsupported versions are rejected. Save validates and atomically
replaces its target using a temporary sibling file; load completes before
replacing the active project.

## Project: `amcad.project`

| Field | Content |
| --- | --- |
| `project` | Persistent project ID and name |
| `component_definitions` | Embedded definitions |
| `component_instances` | UUID, definition ID, name, x/y, clockwise quarter-turn rotation |
| `nodes` | UUID, instance UUID, definition-local port ID, kind |
| `connections` | Logical references plus independent `schematic_geometry` |
| `junctions` | Junction port-node UUID index consistent with nodes |

Connections persist `id`, `from_component_instance_id`, `from_port_id`,
`to_component_instance_id`, `to_port_id`, `from_node_id`, `to_node_id` and:

```json
"schematic_geometry": {
  "points": [[0, 0], [20, 0], [80, 0], [80, 100], [180, 100], [200, 100]],
  "controls": [[80, 0], [80, 100]]
}
```

This illustrative example joins a RIGHT source at [0,0] to a LEFT target at
[200,100]. `points` is the full ordered orthogonal route, including endpoint
leads/adapters. `controls` is the fixed manually arranged interior spine. On
movement/rotation only endpoint-adjacent adapters are rebuilt; controls remain
fixed. A segment/bend edit promotes the edited interior points to controls. Copy
and paste translates points and controls with the component offset. Save/load
preserves exact geometry; crossing jumps and edit handles are not serialized.

All coordinates must be finite; adjacent duplicate points and diagonal segments
are rejected in saved geometry. Saved points must agree with controls and their
current port endpoints. Node UUIDs must agree with the explicit instance/port
pairs. Every port accepts exactly one external line, regardless of object kind.
Multiply occupied ports, malformed references, duplicate IDs/edges, mismatched
node sets, inconsistent geometry and unsupported versions are rejected. Geometry
edits never modify logical endpoint references.

Definitions have `id`, `name`, `prefix`, `category`, `symbol`, `ports`,
`internal_relationships` and nullable future CAD paths. Symbol kinds are `box`,
`external`, `junction`. External interfaces have one port on their symbol's flat
side. Junctions have three/four ports on distinct sides and a central filled dot
with stubs. Junction port occupancy is bounded and all ports share internal
`JUNCTION` relationships. These are hydraulic connectivity metadata, never
physical manifold channels.

Port definitions include `id`, `display_name`, `port_type`, `flow_direction`,
`side`, **`required` (boolean, default true)**, and nullable future local XYZ
position/direction fields. Side is LEFT/RIGHT/TOP/BOTTOM; flow direction is
IN/OUT/BIDIRECTIONAL/UNSPECIFIED. Required unconnected ports determine component
incompleteness; optional ports do not. Completeness is derived, not persisted.

Rotation is clockwise 0/90/180/270 about the symbol center. TOP → RIGHT → BOTTOM
→ LEFT. Definition-local port IDs and sides stay unchanged. External symbols
rotate with their flat-side port. Line lead length is 20 scene units. Zoom,
selection, preview, clipboard and undo history are session-only state.

## Graph: `amcad.hydraulic_graph`

| Field | Content |
| --- | --- |
| `project` | Project metadata |
| `component_instances` | UUID/name and definition identity |
| `nodes` | UUID, instance/port identity, kind, label, type, direction, required flag |
| `junctions` | Junction port-node UUIDs |
| `junction_instances` | UUID/name, port-node IDs, capacity (3/4) |
| `routing_connections` | Explicit instance/port references and node UUIDs; no visual geometry |
| `component_internal_relationships` | Instance UUID, node UUID endpoints, relationship type |

Port labels are INSTANCE.PORT_ID; external interface labels are bare instance
names. IDs are authoritative. Routing edges have `requires_routing: true` and
`direction_semantics: "connectivity_only"`; their endpoint order is not simulated
flow. Internal relationships have no routing flag. Consumers apply internal
JUNCTION relationships to recover common hydraulic nets. Neither geometry edits
nor crossings/jumps create or change graph objects or relationships.

## Legacy migration

V1 single-port junctions convert to 3-Way at degree ≤3 or 4-Way at degree 4,
retaining instance IDs and assigning separate ports to their incident lines.
Degrees above four still require splitting the legacy junction before upgrading.
Definition and additional port IDs are deterministic, and ordinary component
endpoints retain their port identities.

The authorized V1.2 legacy-file migration also handles formerly valid fan-outs
on component/external ports: it adds an explicit 3-Way/4-Way Junction, or bounded
3-Way chain for higher degrees, and retargets the incident lines through its
separate ports. The original port has one new line into that common net.
Existing instances, node IDs, original line IDs and hydraulic terminal nets are
preserved. Added IDs and unique names are deterministic. Overoccupied V1.1
junction ports, invalid endpoints and duplicate records are rejected.

Old lines receive initial orthogonal geometry and all old ports default to
Required unless already marked Optional. Opening never rewrites files. Saving
writes version 3. This migration is limited to old files: the editing UI never
automatically inserts junctions or branches on line clicks.

The original project is preserved in `tests/fixtures/c1_r.v1.json`; the current
sample in `examples/` uses explicit supply/return junctions, manual controls and
crossing jumps without changing its historical hydraulic terminal nets.
