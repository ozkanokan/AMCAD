# V1.3 cavity profile contract

`ComponentDefinition.physical` contains `cavity_type` (NONE or REVOLVED_PROFILE),
`cavity_profile` and `hydraulic_interfaces`. NONE has no profile or interfaces.
Existing files without this block load as NONE. Project and graph schema 4 embed
one definition per definition ID; instances retain only their definition reference.

A profile has a persistent `id`, `schema_version: 1`, `units: "mm"`, ordered
`vertices` and the fixed datum:

```json
{"mounting_face_z_mm": 0, "positive_z": "DEPTH_INTO_MANIFOLD", "revolve_axis_r_mm": 0}
```

Each vertex stores `id`, `z`, `r` and `corner`. Coordinates are finite, R >= 0.
The ordered open profile represents one half-section; it need not close to the
axis. Numeric editor entries support six decimal places and are independent of
mouse grid snap. Negative Z is allowed relative to the fixed mounting datum.

## Corner parameters

SHARP contains no treatment parameters. FILLET stores `radius_mm`; CHAMFER stores
`length_mm` and `angle_deg`. Original theoretical corner coordinates and IDs stay
unchanged. Fillets and chamfers are never serialized as sampled replacement points.

For adjacent rays from the corner to its previous/next points, let their interior
angle be theta. A fillet's tangent setback is radius / tan(theta/2); its center
lies on the angle bisector at radius / sin(theta/2). Rendering uses an arc derived
from these parameters. Radius must be positive and tangent points must fit both
adjacent segments without crossing R=0 or overlapping neighboring treatments.

Chamfer length is the **incoming-segment setback from the theoretical corner**.
Angle is between the incoming segment heading toward that corner and the chamfer
cut heading toward the outgoing segment. The outgoing setback is
length * sin(angle) / sin(theta + angle). Angle must be greater than zero and less
than 180 - theta degrees. At a right-angle corner, a 45-degree chamfer has equal
setbacks. Both setbacks must fit; adjacent treatments cannot overlap.

Endpoint treatments, straight/reversing treated corners, zero/negative dimensions
and impossible setbacks are rejected. Applying an invalid feature is transactional;
SHARP removes a treatment without deleting its original vertex.

## Hydraulic interfaces

Each marker has a persistent `id`, `hydraulic_port_id`, `interface_type`, `z_mm`,
nullable `r_mm`, `nominal_connection_diameter_mm` and `preferred_direction`.
Types are AXIAL/RADIAL; directions are AXIAL_POSITIVE, AXIAL_NEGATIVE, RADIAL or
UNSPECIFIED. Coordinates are finite, supplied R is nonnegative, diameter is positive.
The port ID must exist in the schematic definition. V1.3 allows one marker per
port and rejects duplicate IDs/mappings. Missing required-port mappings warn but
do not block saving a valid profile. NONE definitions need no mappings.

Markers are physical metadata, not schematic nodes or extra hydraulic edges.
The list and separate profile version leave room for future typed geometry and
interface extensions; no future geometry operations are implemented here.

## Validation and preview

Validation detects fewer than two points, consecutive coincident points,
negative R, adjacent retracing, nonadjacent segment intersections/touches and
invalid or overlapping treatments. Additional treated-profile intersection checks
use temporary arc sampling. These checks detect obvious conflicts and are not a
CAD constraint solver or a proof of manufacturability. Stored geometry stays exact;
temporary sampling is never persisted. The preview mirrors the cross-section only.

The parallel check-valve example uses illustrative dimensions, not a commercial
cavity specification. The existing C1–R project remains available and unchanged.
