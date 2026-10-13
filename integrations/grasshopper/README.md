# AMCAD → Rhino 8 / Grasshopper, Phase 1

This folder contains the runnable **Python 3 Script component example**, its
export/placement files, and the RhinoCommon importer. AMCAD supplies exact local
geometry and topology; Grasshopper owns physical transforms. Nothing uses
schematic X/Y coordinates or schematic rotation as physical placement.

## Files

| File | Purpose |
| --- | --- |
| `demo.grasshopper.json` | Single-file physical handoff: two CV instances of one cavity, true R0.5 fillet and 0.5 × 30° chamfer, interfaces, junction connectivity and an external boundary |
| `demo.placements.json` | Independent physical placements; CV1 at origin, CV2 translated and rotated |
| `example_component.py` | Ready-to-paste Rhino 8 Grasshopper Python 3 example |
| `amcad_runtime.py` | Python 3.9+ validation, stable-ID persistence and transform math |
| `rhino_importer.py` | Exact line/arc → revolved RhinoCommon Breps, transformed profiles/interfaces |
| `rhino_host_check.py` | Native Rhino 8 checks; run in ScriptEditor, without adding document objects |
| `sdk_check.py` | Optional standalone OpenNURBS kernel check using `rhino3dm==8.35.0` |
| `demo_project.amcad.json` | Isolated AMCAD source project for the demonstration |
| `make_demo.py` | Regenerate the sample assets from the real AMCAD models |

No AMCAD installation, PySide6 or external Python packages are needed **inside
Rhino 8**: RhinoCommon and Grasshopper are supplied by Rhino. Keep the three
component/importer/runtime Python files together. Use Rhino 8's **Python 3 Script**,
not the legacy IronPython 2 component. The scripts support Rhino's CPython 3.9+.

## Open and run the Grasshopper example

1. Start Rhino 8 and create a blank document with **millimeters** as model units.
   Run `Grasshopper` and create a new definition.
2. Add one **Python 3 Script** component. Use **Script mode**, not SDK mode.
3. Rename/create inputs exactly as follows. Right-click each input to set access
   and type hints; flatten the list inputs so GH does not run per branch.

   | Inputs | Access / hint |
   | --- | --- |
   | `Folder`, `ExportPath`, `PlacementPath` | Item / string |
   | `IDs` | List, Flatten / string |
   | `X`, `Y`, `Z`, `Rx`, `Ry`, `Rz` | List, Flatten / float |
   | `SavePlacements`, `Reload` | Item / bool |

4. Name outputs exactly: `Cavities`, `Profiles`, `InterfaceAxes`,
   `InterfaceFrames`, `InstanceIDs`, `InterfaceMetadata`, `Connectivity`,
   `Transforms`, `Status`. Open the script editor and replace its code with
   **all of `example_component.py`**; do not wrap it in `RunScript`.
5. Connect text Panels containing absolute paths:
   - `Folder`: this `integrations/grasshopper` directory.
   - `ExportPath`: its `demo.grasshopper.json`.
   - Copy `demo.placements.json` to a writable **review folder** as
     `my-demo.placements.json`; connect that path to `PlacementPath`.
   Keep `SavePlacements` **False**, and `Reload` False initially. Leave IDs and
   numeric inputs unwired. The saved placements display two separate cavities.
6. Enable component preview; connect `Cavities` to a Brep parameter and
   `InterfaceAxes` to a Curve parameter if desired. Interface axes are 10 mm
   long, with directions from each transformed position into its routing direction.
   `InterfaceFrames` supplies section planes; section sizes and rotation are in
   `InterfaceMetadata`. Use Rhino Zoom Extents. Connect `Connectivity`, `Status`
   and `InstanceIDs` to Panels.
7. Save this Grasshopper definition as `AMCAD-Phase1.gh`. Opening that saved file
   later restores the component wiring; the JSON paths must remain accessible.

This is a one-component reproducible example, rather than a precompiled `.gh`
whose embedded script would be a second, separately maintained importer.

### Independent slider parameters

Connect this two-line Panel to `IDs` (CV1 first, CV2 second):

```text
11efbfb1-efc4-50ee-86dc-ee4ef1d044e0
5520b2e6-b20f-5296-8abb-eef68be98755
```

For each coordinate, combine two Number Sliders with **Merge**, then connect the
flattened list to the corresponding input. Initial example values:

| Input | CV1 | CV2 |
| --- | ---: | ---: |
| X | 0 | 30 |
| Y | 0 | 10 |
| Z | 0 | 5 |
| Rx | 0 | 15 |
| Ry | 0 | 30 |
| Rz | 0 | 90 |

Translations are millimeters; rotations are degrees. Change only CV2's slider and
confirm CV1 remains unchanged. All nonempty parameter lists must contain one value
per ID; **no implicit broadcasting** occurs. A one-line IDs Panel can target one
instance alone. Empty lists retain saved values. Input bindings use IDs, not names
or branch indices. Tree branches are `{i}` ordered by the `InstanceIDs` output
(sorted stable ID); interfaces within each branch retain definition order.

Set `SavePlacements` True to save the current values atomically to the separate
placement file. While True, subsequent parameter solves also save intentionally;
set it False to stop saving. Disconnect numerical overrides to test recovery from
the file. New export revisions retain positions by component instance ID. New
instances default to identity at origin. Removed IDs remain in the placement file
so temporarily absent instances can recover their values when reintroduced.

Set `Reload` True or use GH's Recompute after replacing an export; the JSON is
read on every solve. Recompute is manual; there is no file watcher. Export and
placement files must be separate. Writers refuse to overwrite project/cavity or
unrelated files. Errors clear outputs and produce a red component runtime message.

## Exporting a real project

In AMCAD, assign independent cavities with complete port mappings, then use
**File → Export to Grasshopper…**. The export uses **project cavity snapshots**,
including their revisions, rather than silently substituting a newer library
revision. Unassigned instances (including legacy embedded cavities) are excluded
from geometry and reported explicitly, while their graph terminals remain available.
Import legacy cavities explicitly and repair/assign them through existing AMCAD
workflows if physical geometry is required. Export does not write library data,
update project schemas or save/dirty the project.

## Exact geometry and coordinate contract

- Theoretical profile vertices remain original `z`/`r` records (`r` is radial Y);
  their IDs and fillet/chamfer parameters are retained exactly.
- AMCAD's existing `surface_patches` evaluator supplies trimmed straight segments
  and circular arcs. Rhino constructs LineCurves and rational arc curves directly,
  joins them and revolves around local +Z; there is no stored tessellation or
  second chamfer convention. The mounting datum is local axial Z=0.
- Embedding is `(local X, local Y, local Z)=(radial Y, 0, axial Z)` at azimuth 0.
  Interface anchors use AMCAD's existing `(r cos φ, r sin φ, z)` convention.
- Placement is a right-handed homogeneous 4×4 local-to-world transform:
  **T × Rz × Ry × Rx**, column vectors, rotations around fixed world axes.
  Points receive rotation and translation; directions and section U/V vectors
  receive rotation only. Curves and Breps use the same matrix.
- `source` interface metadata remains in cavity-local coordinates; the top-level
  position/direction/section-frame fields in GH outputs are world coordinates.
  Geometry carries `amcad.instance_id`, `amcad.cavity_id` and revision user strings.
- Only valid axis-closed revolved profiles and CIRCLE/SLOT/RECTANGLE interface
  sections are supported. Invalid anchors, unsupported types, nonfinite values,
  discontinuous segments, mapping errors and failed Rhino solids are errors.
  No approximation or feature removal is attempted.

Connectivity includes original nodes/edges/internal relationships plus hydraulic
nets. Only wires and explicit **JUNCTION** relationships merge nets. Valve internal
relationships remain separately described and are not shorted into routing nets.
Physical terminals use **instance ID + interface ID**, so two instances sharing
one cavity/interface definition stay distinct. Unassigned terminals are explicit
boundaries. Connectivity is metadata, not generated channel geometry.

## Verification

Run AMCAD's Python 3.14.4 suite from the repository root:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
python -m integrations.grasshopper.make_demo  # Regenerates only these sample files
```

Optional independent geometry SDK check (a separate Python 3.12 environment was
used for this check; AMCAD itself remains Python 3.14.4):

```bash
python -m pip install rhino3dm==8.35.0
python integrations/grasshopper/sdk_check.py
```

For the native host check, open `rhino_host_check.py` in Rhino 8's `ScriptEditor`,
choose Python 3, and run it with a blank millimeter document. Then perform the GH
steps above, move/rotate one instance, toggle saving, and reopen the definition.
The self-test does not bake anything or access user library directories.

Cloud validation covers export, placement, Python 3.9 syntax compatibility and
actual OpenNURBS solids/arcs/transforms. **Rhino 8 / Grasshopper UI execution is not
available in the cloud and must be checked locally.** No automatic routing,
optimization, manifold Booleans, channel solids or placement constraints are added.

## Phase 2 — single-instance placement controller

For a searchable native instance picker and one six-field editor, use the separate
[Phase 2 setup guide](PHASE2.md) and `controller_component.py`. Existing Phase 1
components, geometry, inputs/outputs and placement schema remain unchanged.
