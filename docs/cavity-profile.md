# V1.4 cavity profile contract

`ComponentDefinition.physical` contains `cavity_type` (NONE or REVOLVED_PROFILE),
`cavity_profile` and `hydraulic_interfaces`. NONE has no profile or interfaces.
Existing files without this block load as NONE. Project and graph schema 5 embed
one definition per definition ID; instances retain only their definition reference.

A profile has a persistent `id`, `schema_version: 1`, `units: "mm"`, ordered
`vertices` and the fixed datum:

```json
{"mounting_face_z_mm": 0, "positive_z": "DEPTH_INTO_MANIFOLD", "revolve_axis_r_mm": 0}
```

Each vertex stores `id`, `z`, `r` and `corner`. Coordinates are finite, Y >= 0.
The UI uses Z horizontally and Y vertically; **R means fillet radius only**.
The persisted `r` coordinate, interface `r_mm` and `revolve_axis_r_mm` datum key
remain unchanged for V1.3 compatibility. The profile remains version 1; project
and graph version 5 adds surface-port metadata without changing profile geometry.
The ordered open profile represents one half-section; it need not close to the
axis. The point table shows round-trippable decimal coordinates without discarding
stored precision, independently of mouse grid snap. Numeric editors use the C
locale and periods. Negative Z is allowed relative to the fixed mounting datum.

## Corner parameters

SHARP contains no treatment parameters. FILLET stores `radius_mm`; CHAMFER stores
`length_mm` and `angle_deg`. Original theoretical corner coordinates and IDs stay
unchanged. Fillets and chamfers are never serialized as sampled replacement points.

For adjacent rays from the corner to its previous/next points, let their interior
angle be theta. A fillet's tangent setback is radius / tan(theta/2); its center
lies on the angle bisector at radius / sin(theta/2). Rendering uses an arc derived
from these parameters. Radius must be positive and tangent points must fit both
adjacent segments without crossing Y=0 or overlapping neighboring treatments.

Chamfer length is the **incoming-segment setback from the theoretical corner**.
Angle is between the incoming segment heading toward that corner and the chamfer
cut heading toward the outgoing segment. The outgoing setback is
length * sin(angle) / sin(theta + angle). Angle must be greater than zero and less
than 180 - theta degrees. At a right-angle corner, a 45-degree chamfer has equal
setbacks. Both setbacks must fit; adjacent treatments cannot overlap.

Endpoint treatments, straight/reversing treated corners, zero/negative dimensions
and impossible setbacks are rejected. Applying an invalid feature is transactional;
SHARP removes a treatment without deleting its original vertex.

Mutual exclusion is validated in the model, including on load: SHARP contains no
parameters, FILLET contains no chamfer length/angle, and CHAMFER contains no radius.
Editing the table's positive R or Chamfer value installs the respective feature
and clears the other. Zeroing an active dimension removes the treatment; inactive
zeros do not remove another active feature. A new chamfer defaults to 45°; changing
its length preserves its existing angle, including non-45° saved angles.

Append/insertion changes only the vertex list; existing UUIDs, coordinates and
corner parameters remain intact. Insertion/deletion/coordinate changes that make
installed treatment geometry impossible are rejected transactionally. Other draft
errors may remain visible as INVALID and cannot be saved. No edit silently tunes
or deletes a corner feature.

Renderer and dimension annotations share the model's exact `features()` geometry.
Radius leaders target the derived arc midpoint; chamfer leaders target the cut
midpoint. The main profile is trimmed; selectable handles remain on theoretical
vertices. Selected/hovered treatments show dashed extensions to the original corner.
Text/leaders remain a constant display size while zooming. Placement avoids obvious
profile/label overlap where space permits; crowded views may still need zooming.
Annotations, construction lines, tangent points and live drawing previews are not
persisted and never alter authoritative geometry.

## Hydraulic interfaces

Each marker has a persistent `id`, `hydraulic_port_id`, `interface_type`, `z_mm`,
nullable `r_mm`, `nominal_connection_diameter_mm` and `preferred_direction`.
Legacy types are AXIAL/RADIAL; directions are AXIAL_POSITIVE, AXIAL_NEGATIVE, RADIAL or
UNSPECIFIED. Coordinates are finite, supplied Y is nonnegative, diameter is positive.
The port ID must exist in the schematic definition. V1.3 allows one marker per
port and rejects duplicate IDs/mappings. Missing required-port mappings warn but
do not block saving a valid profile. NONE definitions need no mappings.

Markers are physical metadata, not schematic nodes or extra hydraulic edges.
The list and separate profile version leave room for future typed geometry and
interface extensions. V1.4 adds SURFACE anchors, normalized 3D direction, channel
sections/rotation and visualization length; see [cavity-surface.md](cavity-surface.md).

## Validation and preview

Validation detects fewer than two points, consecutive coincident points,
negative Y, adjacent retracing, nonadjacent segment intersections/touches and
invalid or overlapping treatments. Additional treated-profile intersection checks
use temporary arc sampling. These checks detect obvious conflicts and are not a
CAD constraint solver or a proof of manufacturability. Stored geometry stays exact;
temporary sampling is never persisted. The mirrored cross-section remains available;
V1.4 also revolves evaluated segments/arcs into an open visualization mesh.

The parallel check-valve example uses illustrative dimensions, not a commercial
cavity specification. The existing C1–R project remains available and unchanged.
