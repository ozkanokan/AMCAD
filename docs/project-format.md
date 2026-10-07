# V1.1 project and graph contracts

Both formats are UTF-8, human-readable JSON with `schema` and integer
`schema_version`. Current version is **2**. Version 1 projects migrate explicitly
on load; graph exports are output-only. Unsupported versions are rejected.
Project save is atomic: validation and serialization finish in a temporary
sibling file before replacing the target. Loading completes before replacing the
open project, so invalid files do not destroy the current session.

## Project: `amcad.project`

| Field | Content |
| --- | --- |
| `project` | Persistent project `id` and human-readable `name` |
| `component_definitions` | Definitions used or embedded in the project |
| `component_instances` | UUID `id`, `definition_id`, unique `name`, `x`, `y`, `rotation` |
| `nodes` | UUID `id`, `instance_id`, definition-local `port_id`, `kind` |
| `connections` | UUID `id`, node UUIDs and explicit instance/port references at both ends |
| `junctions` | Junction port-node UUID index, consistent with `nodes` |

Every connection persists `from_component_instance_id`, `from_port_id`,
`to_component_instance_id`, `to_port_id`, `from_node_id`, `to_node_id` and `id`.
The node UUIDs must resolve to the same instance/port pairs; disagreement is
rejected. Renaming, movement and rotation never rewrite these identities.
Malformed references, duplicate IDs/edges, mismatched node sets, overoccupied
junction ports and unsupported versions are rejected during load/save validation.

Each definition has `id`, `name`, `prefix`, `category`, `symbol`, `ports`,
`internal_relationships` and nullable `component_cad_path`, `cavity_cad_path`,
`keepout_cad_path`. A symbol has `kind` (`box`, `external` or `junction`), width
and height. External ports have exactly one port. Junctions have exactly three
or four ports, each on a distinct side and each accepting one routing connection.

Port definitions contain `id`, `display_name`, `port_type`, `flow_direction`,
`side`, nullable `local_position_xyz` and `local_direction_xyz`. Flow direction
is `IN`, `OUT`, `BIDIRECTIONAL` or `UNSPECIFIED`; symbol side is `LEFT`, `RIGHT`,
`TOP` or `BOTTOM`. Port geometry and CAD paths are reserved metadata and have
no V1.1 behavior.

Internal relationships contain `from_port_id`, `to_port_id`, and a
`relationship` label. Generic components have no assumed internal behavior.
A relief valve may declare an `IN → OUT` `RELIEF_VALVE` relationship. Junction
ports are joined into one common hydraulic net with internal `JUNCTION`
relationships. These relationships are never physical routing connections.

Schematic coordinates are scene units; clockwise rotation is 0, 90, 180 or 270
about the symbol center. Port sides rotate TOP → RIGHT → BOTTOM → LEFT → TOP.
A full turn normalizes to 0. Definition-local port sides/IDs remain unchanged.
The graphical position and global side are computed from the instance transform.
Wires have 20-unit orthogonal outward leads at both ends; the destination lead
is traversed in reverse when arriving. No pixel geometry appears in connections.
Zoom, selection, clipboard and undo history are session state, not project content.

Node `kind` is `component_port`, `external_port`, or `junction`. Junction instances
provide the position of a small central dot and its three/four connectable ports.
Their internally connected port nodes remain distinct, permitting occupancy
validation and directional leads. Crossings create no graph object; wire-click
branching is not implemented.

## Graph: `amcad.hydraulic_graph`

| Field | Content |
| --- | --- |
| `project` | Project metadata |
| `component_instances` | UUID, name, definition ID and definition name |
| `nodes` | Node UUID, instance UUID, port ID, kind, label, type, flow direction |
| `junctions` | Junction port-node UUIDs |
| `junction_instances` | Junction instance UUID/name, `port_node_ids`, `capacity` (3 or 4) |
| `routing_connections` | Explicit instance/port pairs and node UUID edges; `requires_routing: true` |
| `component_internal_relationships` | Instance UUID, node UUID endpoints, relationship type |

Port labels are `INSTANCE.PORT_ID`, with bare names only for external interfaces.
Labels are descriptive; persistent references are authoritative. Routing edges
have `direction_semantics: "connectivity_only"`: `from` and `to` retain creation
order and do not impose flow. `requires_routing` classifies future routing input;
it does not claim V1.1 computes physical routes. Internal relationships have no
routing flag and are never inserted into the routing connection list. Consumers
must apply junction internal relationships to recover their common hydraulic net.

## Version 1 compatibility

Opening a V1 project fills explicit instance/port endpoint references from its
existing node UUIDs. A legacy single-port junction is converted to 3-Way when
its degree is at most three, or 4-Way when its degree is four. Its instance UUID,
name, schematic position/orientation, connection UUIDs and non-junction endpoints
are preserved. Each incident connection gets its own junction port, preferring
the side facing its neighbor. Junctions receive internal common-net relationships.
The first assigned port keeps the old junction node UUID; remaining port and
definition UUIDs are derived deterministically. Repeated loads produce identical
migrated data. Saving writes version 2; opening never rewrites the original file.

Legacy junctions with more than four branches cannot fit either bounded type and
are rejected with a clear instruction to split them before upgrading. Invalid
legacy references, duplicate edges and inconsistent junction indexes are rejected
rather than repaired silently. The original `examples/c1_r.amcad.json` remains a
V1 compatibility sample; its corresponding graph example is exported as version 2.
