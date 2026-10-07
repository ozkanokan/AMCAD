# V1 project and graph contracts

Both formats are UTF-8, human-readable JSON with `schema` and integer
`schema_version`. Current version is **1**. Project save is atomic: validation
and serialization finish in a temporary sibling file before replacing the target.
Malformed graph references, duplicate IDs/edges, mismatched node sets and unsupported
versions are rejected on project load. Loading completes before replacing the
open project, so invalid files do not destroy the current session.

## Project: `amcad.project`

| Field | Content |
| --- | --- |
| `project` | Persistent project `id` and human-readable `name` |
| `component_definitions` | Definitions used or embedded in the project |
| `component_instances` | UUID `id`, `definition_id`, unique `name`, `x`, `y`, `rotation` |
| `nodes` | UUID `id`, `instance_id`, definition-local `port_id`, `kind` |
| `connections` | UUID `id`, `from_node_id`, `to_node_id` |
| `junctions` | Explicit junction node UUID index, consistent with `nodes` |

Each definition has `id`, `name`, `prefix`, `category`, `symbol`, `ports`,
`internal_relationships` and nullable `component_cad_path`, `cavity_cad_path`,
`keepout_cad_path`. A symbol has `kind` (`box`, `external` or `junction`), width
and height. External and junction symbols must each have exactly one port.

Port definitions contain `id`, `display_name`, `port_type`, `flow_direction`,
`side`, nullable `local_position_xyz` and `local_direction_xyz`. Flow direction
is `IN`, `OUT`, `BIDIRECTIONAL` or `UNSPECIFIED`; symbol side is `LEFT`, `RIGHT`,
`TOP` or `BOTTOM`. Port geometry and CAD paths are reserved metadata and have
no V1 behavior.

Internal relationships contain `from_port_id`, `to_port_id`, and a
`relationship` label. Generic components have no assumed internal behavior.
A relief valve may declare an `IN → OUT` `RELIEF_VALVE` relationship. This
metadata is kept separate from physical manifold channel connectivity.

Schematic coordinates are scene units; rotation is 0, 90, 180 or 270 degrees
about the symbol center. Wire paths are recomputed from port layout and instance
transforms, so no pixel coordinates appear in connection records. Zoom, selection,
clipboard and undo history are session state, not project content.

A node's `kind` is `component_port`, `external_port`, or `junction`. External
interfaces are modeled by one-port instances to share placement, rotation and
naming mechanics while remaining individual graph nodes without internal behavior.
Junction instances similarly provide the graphical position for explicit junction
nodes. Junctions can have arbitrary graph degree. Crossings create no graph object.

## Graph: `amcad.hydraulic_graph`

| Field | Content |
| --- | --- |
| `project` | Project metadata |
| `component_instances` | UUID, name, definition ID and definition name |
| `nodes` | Node UUID, instance UUID, port ID, kind, label, type, flow direction |
| `junctions` | Explicit junction node UUIDs |
| `routing_connections` | User-created UUID endpoint edges; `requires_routing: true` |
| `component_internal_relationships` | Instance UUID, node UUID endpoints, relationship type |

Port labels are `INSTANCE.PORT_ID`, with bare names for external interfaces and
junctions. Labels are descriptive; UUIDs are authoritative. Routing edges have
`direction_semantics: "connectivity_only"`: `from` and `to` retain creation order
and do not impose flow. `requires_routing` classifies these as future routing input;
it does not claim V1 computes routes. Internal relationships have no routing flag
and are never silently inserted into the routing connection list.

See the complete files in `examples/` for real IDs and data. Exported graphs are
an output format; V1 loads projects, not graph exports.
