# V1.4 surface and hydraulic port contract

The existing profile version 1 remains authoritative: original Z/r vertices, UUIDs,
parametric corner features and fixed Z=0/Y=0 datum. Project/graph version 5 introduces
optional hydraulic-interface fields; versions 1–4 still load. Definitions are shared
by instances, including all cavity and port data. No visualization mesh is serialized.

## Revolved coordinates and anchors

Evaluate the profile using `CavityProfile.features()`: trimmed straight segments,
circular fillets and chamfer cuts. Revolve a point (z,r) as:

`XYZ = (r*cos(phi), r*sin(phi), z)`

Circumferential angle phi is in degrees from +X toward +Y, viewed from +Z.
Z is positive depth; the sketch's nonnegative radial Y is still persisted as `r`.
In physical projections, actual Y may be negative. The surface's endpoint rings
remain open. There are no end caps, artificial axis-closing segments or volume.

`surface_anchor` contains:

| Field | Meaning |
| --- | --- |
| `kind` | LINE, FILLET or CHAMFER |
| `vertex_id` | Theoretical vertex UUID; incoming endpoint for LINE |
| `next_vertex_id` | Adjacent outgoing vertex UUID for LINE; null for corner features |
| `t` | Normalized [0,1] position along the evaluated segment/feature |
| `angle_deg` | Circumferential angle |

Line parameters refer to the current trimmed straight segment between the same
ordered adjacent theoretical vertex pair. Corner parameters refer to the same
UUID **and feature type**. Geometry changes recompute positions from these anchors.
Insertion breaking a vertex pair, deletion or replacing FILLET with CHAMFER cannot
retarget an anchor. Resolution fails explicitly and the UI reports INVALID anchor.
Unresolved anchors are retained in JSON and hidden from geometry previews; choose
an explicit feature in the port dialog to reattach. No nearest-surface migration
occurs. Missing/invalid scalar IDs/parameters or schematic port IDs are rejected.

Picking uses frontmost triangles of a software-rendered visualization mesh and
interpolates their parametric coordinates. Final XYZ resolves from exact evaluated
profile geometry; approximate picked mesh XYZ is never authoritative. Default mesh
resolution is 64 angular divisions and 16 subdivisions per 90° fillet. Triangles,
transient pick data, derived XYZ and camera state are presentation-only.

## Channel definition and local frame

Each `HydraulicInterface` retains its ID, schematic `hydraulic_port_id`, legacy
coordinate/type/direction/nominal-diameter fields, and adds:

| Field | Meaning |
| --- | --- |
| `surface_anchor` | Parametric anchor above, or null for legacy fixed position |
| `direction` | Normalized [dx,dy,dz], or null for compatible legacy defaults |
| `section` | ChannelSection below, or null for a legacy nominal-diameter circle |
| `section_rotation_deg` | Rotation in the perpendicular local section plane |
| `preview_length_mm` | Positive finite visualization-only length; default 10 |

New surface ports use `interface_type: "SURFACE"`. Their legacy z/r fields may
contain cached axial/radial values; anchored resolution always takes precedence.
XYZ is derived by `interface_pose()` and displayed in the dialog. It is not an
independent coordinate capable of overriding the anchor. Arbitrary nonzero finite
directions normalize safely; existing unit vectors retain their values on reload.
New ports initialize direction from the local wall normal, toward increasing radial
distance where the wall permits it; shoulder normals follow profile traversal.
Explicitly edited directions may point anywhere and never constrain routing.

Section types:

- CIRCLE: `diameter_mm` > 0.
- SLOT: `width_mm` > 0, `length_mm` >= width; length is the total capsule length.
- RECTANGLE: `width_mm` > 0, `height_mm` > 0.

Inactive section dimensions keep default metadata. Circle channel diameter and the
legacy nominal connection diameter are independent editable values. Slots use local
U as their long axis; rectangles use U for width and V for height.

To build a deterministic perpendicular frame, choose the world axis least aligned
with normalized direction D (ties X, Y, Z). Set U = normalize(reference × D),
V = D × U. For section rotation a, U' = U*cos(a)+V*sin(a),
V' = -U*sin(a)+V*cos(a). Extrusion starts at resolved XYZ and ends at
XYZ + D*preview_length_mm. Its capped channel mesh is visualization only; it is
never intersected with, trimmed from or subtracted from the uncapped cavity surface.

## Legacy behavior and limitations

Unanchored records remain at (0, r_mm or 0, z_mm). Explicit legacy axial-positive/
negative or radial preferred directions take precedence; otherwise AXIAL defaults
+Z and RADIAL defaults +Y. Section defaults to a circle of the nominal diameter.
Legacy records remain loadable without mesh creation, forced anchoring or altered
profile/end semantics. The original sample projects remain unchanged; their graph
exports are refreshed to version 5. A separate 3D demo stores explicit surface ports.

The renderer uses Qt QPainter, orthographic projections and an orbitable orthographic
ISO camera. Transparent faces are depth sorted; overlapping faces/channels can have
visual artifacts. Picking selects the nearest visible cavity mesh triangle, not a
CAD intersection. Very dense profiles can render slowly. Save may retain invalid
anchors for explicit repair; warnings and table status remain visible after reopen.
There are no CAD solids, manufacturing tolerances, Boolean operations, surface
trimming, drilling intersections, Rhino/STEP integration, routing or CFD.
