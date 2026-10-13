# Phase 2 — Single-instance placement controller

The existing Phase 1 component and its inputs/outputs are unchanged. Phase 2 adds
one separate Python 3 component and a compact **native Rhino/Eto modeless editor**.
There are six numeric fields total, a searchable instance list, and Apply, Save All
and Reload buttons. No third-party GH plugins or per-cavity sliders are needed.

The controller uses the same `amcad.placements` schema **1**, mm units and
**T × Rz × Ry × Rx** transform order. It delegates all geometry, interface axes,
frames and connectivity to the unchanged Phase 1 importer/runtime. Schematic
coordinates and viewport Gumball moves are never read as placement parameters.

## Reproducible Grasshopper setup

1. Open Rhino 8 with a millimeter document. Open `AMCAD-Phase1.gh` and **Save As**
   `AMCAD-Phase2.gh`, preserving your tested Phase 1 definition.
2. Add a **Python 3 Script** component in **Script mode**, not SDK mode. Create
   these six inputs with the exact names and settings:

   | Input | Access | Type hint | Connection |
   | --- | --- | --- | --- |
   | `Folder` | Item | str/string | Panel: absolute `integrations/grasshopper` directory |
   | `ExportPath` | Item | str/string | Panel: your AMCAD Grasshopper export |
   | `PlacementPath` | Item | str/string | Panel: separate writable placement JSON path |
   | `Edit` | Item | bool | Momentary GH Button |
   | `Save` | Item | bool | Momentary GH Button |
   | `Reload` | Item | bool | Momentary GH Button |

   `PlacementPath` is required, but the file may be new. Its parent directory must
   exist. Use your existing Phase 1 placement file to preserve current placements.
   For the isolated demo, copy `phase2-seven.placements.json` to a review folder
   and use `phase2-seven.grasshopper.json` as the export.
3. Create these exact output names:

   | Output | Meaning |
   | --- | --- |
   | `Cavities`, `Profiles` | World geometry trees, as in Phase 1 |
   | `InterfaceAxes`, `InterfaceFrames` | The same instance transform applied to interfaces |
   | `InstanceIDs` | Stable IDs in geometry-tree branch order |
   | `InterfaceMetadata` | World interface metadata, as in Phase 1 |
   | `Connectivity` | Unchanged export connectivity JSON |
   | `Transforms` | 16 row-major matrix entries per tree branch |
   | `PlacementState` | Complete placement JSON, including temporarily absent IDs |
   | `SelectedInstance` | Selected human-readable schematic name |
   | `CurrentPlacement` | Selected ID, name, translation, rotation and matrix as JSON |
   | `Status` | Active count, selection and saved/unsaved status |

4. Replace the component's script with **all of `controller_component.py`**. Keep
   `placement_controller.py`, `placement_editor.py` and Phase 1 modules in Folder.
   Disable **preview** on the old Phase 1 component to avoid duplicate display;
   its code and saved wiring can remain intact.
5. Connect `Cavities` to a Brep parameter and `InterfaceAxes` to a Curve parameter,
   and connect `Status`, `SelectedInstance` and `CurrentPlacement` to Panels.
6. Press **Edit**. The native window opens. Search/select an instance by its
   schematic name; its own applied X/Y/Z/Rx/Ry/Rz values load into the six fields.
7. Edit numbers using decimal periods. Press **Apply / Update Selected**. Only that
   instance changes, and GH schedules a preview update. Other poses are retained.
8. Press **Save All Placements** in the window or the GH **Save** Button to persist
   the complete applied state. **Reload Saved Placements** restores that state.
   Save the GH definition as well to preserve its wiring and file paths.

No ready-to-open `.gh` is generated in the cloud: a Rhino 8/GH host is required to
create and validate native component serialization. The one-component setup above
is the reproducible example; save it once as your local `.gh` file.

## Predictable editing rules

- Selecting another instance loads its stored pose; it never applies the old
  fields. Unapplied field edits are discarded when switching instances.
- Apply is the only field-to-state operation. No text-change, selection-change or
  GH recompute automatically commits numeric fields.
- Search preserves pending edits for the same selection. If the selected row is
  filtered out, editing is disabled until it is visible again.
- Save writes **applied placements only**. The window asks you to apply/discard
  pending text before saving. The GH Save Button saves committed state directly.
- The window confirms Reload when edits would be discarded. The GH Reload Button
  is an explicit discard/reload command, so use it deliberately. Missing or invalid
  saved files produce an error and leave current state intact.
- GH Button commands run on rising edges. A held Toggle does not replay Save or
  Reload when selection changes. Use momentary Buttons; do not trigger Save and
  Reload together.
- Closing the editor retains applied state for this open GH document; reopening
  Edit restores it. **Save placements before closing/reopening the GH definition
  or Rhino.** A GH file save alone does not serialize the controller's live state.
- Switching project/placement paths is blocked while the previous session has
  unsaved placements or pending field edits. Save, or reload/discard, first.
- Geometry is cached across selection-only solves. Applied transforms or changed
  export data rebuild the preview using the existing Phase 1 importer.

Exports are read on every GH solve. After replacing an AMCAD export, use GH
Recompute (F5) or Reload. Existing IDs retain their poses across revision changes,
renames, reordered exports, and new geometry. New IDs default to identity at the
origin. Missing IDs remain in the placement file and recover if reintroduced.
Instance names are presentation only; all persistence and editing binds stable IDs.
Multiple controller components have independent document/component sessions; avoid
using two active writers against the same placement file.

## Seven-instance acceptance workflow

Use the included seven-instance export and a review copy of its placement file:

1. Edit → select **CV1**; set X to **50** and Apply.
2. Select **CV2**. Confirm it loaded its own original X=25, not CV1's 50.
3. Set Y to **30** and Apply.
4. Select CV1 again: X remains 50. Select CV2 again: Y remains 30.
5. Verify CV3–CV7 retained their initial poses.
6. Save All Placements, save/close the GH definition, then reopen it.
7. Edit → select CV1 and CV2 and verify the same values.
8. Change a field without applying, switch instances, and verify no pose was
   accidentally overwritten. Try this with a saved file and with new identity poses.

`controller_host_check.py` can also be opened/run in Rhino 8 **ScriptEditor Python
3** with a millimeter document. It exercises real Eto list/field events, performs
this A/B acceptance sequence in a temporary directory, verifies persistence and
seven valid Rhino solids, and leaves a review editor open. Closing it removes only
its temporary data. It does not access user libraries or existing placement files.

## State API for future algorithms

`placement_controller.py` imports no Rhino, GH or UI packages. Example:

```python
from placement_controller import PlacementController
import amcad_runtime as runtime

controller = PlacementController(export_data, placement_path, export_path)
records = controller.parameters()  # active instance ID/name, pose and 4×4 matrix
controller.update_many({
    records[0]['instance_id']: runtime.pose([50, 0, 0], [0, 0, 0]),
    records[1]['instance_id']: runtime.pose([0, 30, 0], [0, 15, 90]),
})  # atomic validation; other placements are retained
controller.save()
```

`select(id)` and `selection_token` support explicit selected editing.
`apply_selected(translation, rotation, token)` rejects stale A→B and A→B→A edit
callbacks. `snapshot()` returns the complete schema-1 state; `parameters()` returns
active optimization inputs only. Returned data is a copy; commit changes with
`update_many`. Programmatic updates are thread-guarded and invalidate an editor's
old token if its selected pose changes. Refresh/schedule GH afterward to update
native UI and geometry. No optimization or constraint solver is implemented.

## Verification and limits

From AMCAD's Python **3.14.4** environment:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
python -m integrations.grasshopper.make_phase2_demo  # Only Phase 2 sample assets
```

Automated checks exercise seven-instance acceptance, 20/50-instance catalogs,
independence, stale callbacks, atomic updates, schema-1 persistence, orphan/new IDs,
renames/revisions, interface transforms and Phase 1 compatibility. Native Eto/GH
UI execution cannot be run in this Linux cloud; its local host check is supplied.
The Phase 1 geometry evaluator/importer, export/connectivity contract, and existing
project/cavity library files remain unchanged. No collision detection, routing,
optimization, manifold Booleans, Gumball synchronization or unrelated UI work is added.
