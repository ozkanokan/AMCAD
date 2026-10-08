# AMCAD — Hydraulic Manifold Schematic Editor (V1.3a)

A standalone Python / PySide6 desktop editor for hydraulic schematics and their
graph foundation. V1.3a refines the dedicated axisymmetric cavity sketcher with
an editable engineering point table, Draw/Edit modes, parametric corner leaders,
physical hydraulic-interface mappings and a mirrored cross-section preview.
Existing manual line editing, component wizard, JSON projects, undo/redo and
graph export remain available. No CAD kernel, physical manifold routing,
hydraulic simulation or 3D geometry generation is implemented.

## Setup and run

The target is **Python 3.14.4**, pinned in `.python-version`. Dependencies are
PySide6 6.11.2 and pytest 9.1.1. Run from the repository root.

```bash
python --version  # Must report Python 3.14.4
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app.main
# Open the demo:
python -m app.main examples/c1_r.amcad.json
```

Recreate an older disposable `.venv` with Python 3.14.4; upgrading packages does
not change its Python runtime. With `uv`, use `uv python install 3.14.4`, then
`uv venv --python 3.14.4 .venv` to create the environment.

Interactive use requires a desktop session. Linux needs Qt display libraries;
PySide6 Linux x86_64 wheels require glibc 2.34+. Headless/cloud checks:

```bash
python -m pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen python -m pytest -q
QT_QPA_PLATFORM=offscreen python -m app.main examples/c1_r.amcad.json --smoke
```

All **211 tests** and both sample application launch checks pass on Python 3.14.4 under
Linux. Tests exercise the wizard, drag/drop, manual drawing, segment and bend
drags, rotation, single-line occupancy, geometry persistence, undo/redo,
copy/paste, legacy migration, completeness, crossings and graph export. Cavity tests cover
point editing, snap, exact corner features, validation, port mappings, shared
definitions, library/project persistence and GUI save/reopen. V1.3a checks also
exercise treated-corner dragging, marker placement followed by editing, Escape
cancellation, feature preservation during insertion, and decimal periods under
a non-English default locale.
`--smoke` renders the actual window and exits. Native Windows/macOS displays and
executable packaging have not been validated.

## Editing

- The Component Library is docked on the **right**. Drag components onto the
  canvas, or double-click a library entry to place at the view center.
- Drag component bodies to move. Click to select, Ctrl-click to extend selection,
  or drag empty canvas for a selection rectangle. Double-click a component or
  press F2 for its name/orientation and persistent IDs.
- **Draw Line:** click a free port. A dashed live preview follows the cursor on
  the current horizontal/vertical axis. Click empty canvas to fix a bend and
  turn 90 degrees; repeat as needed. Click a free target port to finish.
  Escape or right-click cancels without creating a connection. You may also
  connect ports without adding manual bends.
- Every port accepts **one external line**, including component, external and
  junction ports. A second line is rejected without replacing the first. An
  occupied target leaves the drawing in progress so you can choose a free port.
- **Edit Line:** click a completed line. Round handles appear at internal segment
  midpoints and bends. Drag horizontal segments vertically, vertical segments
  horizontally, or bend handles to rearrange the route. Port endpoints are
  locked. Choose Edit → Delete Line, or press Delete, to remove selected lines.
- **Branching:** add a 3-Way Junction (Ctrl+J) or 4-Way Junction (Ctrl+Shift+J),
  then connect each branch to a distinct port. Each symbol has a filled center,
  short stubs and three/four hollow endpoint ports. Deleting a line frees its port.
  Clicking an existing line never splits it or inserts a junction.
- Ctrl+R rotates selection clockwise by 90 degrees. Ports retain their logical
  identity. TOP → RIGHT → BOTTOM → LEFT; a full turn returns to 0.
- Ctrl+C / Ctrl+V copies selected components and internal lines, including their
  geometry translated with the paste offset. IDs are fresh and names unique.
  Connections outside the selection are omitted; the clipboard is session-local.
- Ctrl+Z / Ctrl+Shift+Z undo/redo schematic and line-geometry edits (100 states).
  Definition creation in the persistent library is not part of schematic history.
- Delete removes selected components and incident lines, or selected lines.
  Mouse wheel zooms, middle-button drag pans, and F fits the schematic.
- File → Save/Open preserves components, positions, rotations and manual line
  geometry. File → Export Hydraulic Graph (Ctrl+E) exports logical connectivity.
  New, Open and Close guard unsaved changes.

Line endpoints have 20-unit orthogonal leads following their global port side.
Manual controls remain fixed when a component moves or rotates; endpoint-adjacent
adapters adjust while the internal route stays arranged. Logical references never
change. Routing here is 2D schematic drawing, without obstacle avoidance.

Unrelated lines crossing strictly inside their segments receive a small graphical
semicircular jump: the lexically larger persistent line ID gets the jump. Parallel
or overlapping segments are not jump candidates. Jumps do not create nodes,
connections or netlist relationships. Explicit junctions are the only branching
objects. Endpoint order records creation order, not simulated flow.

## Component / Port Wizard and completeness

Use **+ New Component**. Set name, prefix, category and port count (1–32). For
each port choose a unique ID, display name, type, flow direction, symbol side and
**Required / Optional** status. Row order controls spacing and the preview is live.
Ports default to Required, including definitions loaded from older projects.

An unconnected required port gives its component an amber outline/accent and its
port a subtle amber fill. The indication clears when all required ports have a
line and returns immediately when a line is deleted. Optional unconnected ports
do not make a component incomplete. Feedback also applies to external interfaces
and junctions; it does not interrupt editing with dialogs.

Optional internal relationships identify two definition port IDs and a relationship
type. These stay separate from physical routing connections and do not simulate
hydraulics. Cavity interface mappings are separate physical metadata; future CAD paths
remain reserved.

Custom definitions are JSON files under `$XDG_DATA_HOME/amcad/components`, or
`~/.local/share/amcad/components`. On Windows, set `XDG_DATA_HOME` to a preferred
writable data directory if desired. Projects embed their definitions, and their
embedded definitions become available in the panel when opened. Invalid custom
library files are reported in the status bar while valid files remain usable.

## Axisymmetric cavity sketcher

In **+ New Component**, configure schematic port IDs first, then click **Cavity
Profile…**. To edit an existing definition, select its placed component or library
entry and choose **Component → Edit Definition Cavity…** (Ctrl+Shift+C), or use
the component properties dialog. The cavity belongs to the reusable definition:
all instances share one profile and the same schematic port identities.

- Choose NONE or REVOLVED_PROFILE. New empty profiles start in **Draw mode**;
  populated profiles start in **Edit mode**. Draw or **Add Point** appends vertices
  on empty canvas clicks, with a snapped live preview. Existing point clicks select
  without adding duplicates. Edit mode selects/drags points and never appends them.
- The point table contains **# | Z (mm) | Y (mm) | R (mm) | Chamfer (mm) | Angle (°)**.
  Rows show original theoretical coordinates; each row retains a hidden vertex UUID.
  Table/sketch selection stays synchronized. Numeric edits update immediately,
  retain floating-point precision, use decimal periods and bypass grid snapping.
- Z is horizontal depth, Y is nonnegative vertical radial distance, and **R means
  fillet radius only**. Y=0 is the fixed revolve axis; Z=0 is the mounting face and
  positive Z is depth into the manifold. Snap offers OFF, 0.1, 0.5 and 1 mm.
- At an internal vertex, enter R > 0 to activate FILLET, or Chamfer > 0 to activate
  CHAMFER; these features replace each other. Chamfer Angle starts at 45° and is
  directly editable. Zero the active dimension to return to SHARP; angle is inactive
  without a chamfer. No separate Apply button is needed.
- Corner treatments never move or replace theoretical vertices. The finished profile
  uses derived arcs/trimmed segments, with automatic radius/chamfer leaders. Selecting
  or hovering a treated point shows subtle dashed theoretical edge extensions.
  Dragging it recomputes geometry while preserving its feature parameters and ID.
- **Insert After Selected** arms the next canvas click; **Delete Point** removes
  the selected vertex. Unaffected IDs and treatments survive append/insert/delete.
  Impossible treatment changes are rejected and the previous value is restored.
  Other draft errors show explicit INVALID feedback and block Save.
- **Place Interface** adds a distinct marker mapped to an existing schematic port
  ID. Set AXIAL/RADIAL, Z/Y, nominal diameter and preferred direction. Duplicate or
  nonexistent port mappings are rejected; missing required mappings produce warnings.
- Markers are independently selectable; double-click one or choose **Edit Selected
  Interface** to edit it. Placement finishes cleanly and preserves Draw/Edit mode.
  The marker section can collapse to leave more room for the point table.
- Escape cancels marker placement, cancels an active drag, switches Draw to Edit,
  or clears Edit selection; committed geometry remains. It never closes the sketcher.
  Save, Cancel and window close explicitly finish the editor; child dialogs keep
  their normal Escape behavior.
- **Revolve Preview** mirrors the section around Y=0. It does not generate a solid.
  Save/reopen preserves exact vertices, UUIDs, corner parameters and interfaces.

Accepting an edit to a placed definition updates the project and participates in
project undo/redo. Existing custom-library definitions are also saved; library
writes are independent of project history. Project-only definitions stay embedded.
Editing a built-in library entry without a placed instance creates a custom copy.
Cancel leaves the original definition untouched.

Existing V1.3 profiles keep their saved `z`/`r` fields and datum; `r` displays as Y.
Dimension leaders and tangent points are derived and never become saved vertices.
See [cavity geometry conventions](docs/cavity-profile.md) for the exact parameter
meaning, datum and validation limits.

## Parallel check-valve physical demo

Open [the separate project](examples/parallel_check_valves.amcad.json): IN → J1
branches into CV1 → OUT1 and CV2 → OUT2. Both valves reference the **same**
Illustrative Check Valve definition, with IN/OUT physical mappings, a fillet and
a chamfer. Its dimensions demonstrate the workflow and are **not a commercial
valve cavity standard**. The [definition](examples/illustrative_check_valve.component.json)
and [graph export](examples/parallel_check_valves.graph.json) are included.

```bash
python -m app.main examples/parallel_check_valves.amcad.json
QT_QPA_PLATFORM=offscreen python -m app.main examples/parallel_check_valves.amcad.json --smoke
# Regenerate only this demonstrator:
python -m examples.create_physical_demo
```

## C1–R sample

Open [the project](examples/c1_r.amcad.json) to see six instances, fourteen port
nodes, two explicit 3-Way Junctions, six manually arranged routing lines and five
internal relationships (four junction links and one relief-valve relationship).
The [graph export](examples/c1_r.graph.json) records the same connectivity.

- Supply branch: C1.port ↔ J1.LEFT, J1.RIGHT ↔ EHSV1.C1,
  J1.BOTTOM ↔ RV1.IN.
- Return branch: EHSV1.R ↔ J2.BOTTOM, RV1.OUT ↔ J2.RIGHT,
  J2.LEFT ↔ R.port. J2 is rotated 180 degrees in the sample.
- EHSV1.P and EHSV1.C2 are intentionally Optional and unconnected.
- Manual controls deliberately create crossings to demonstrate jump rendering.

Adding J2 replaces the historical implicit branch at R; the original hydraulic
nets are unchanged. `python -m examples.create_demo` regenerates both examples.
The original V1 project is retained under `tests/fixtures/c1_r.v1.json` to validate
backward compatibility.

## Architecture and persistence

`core/` is pure Python: component definitions/instances, port nodes, connections,
project validation/persistence, history, library, graph export and 2D line geometry.
`ui/` contains QGraphicsScene/QGraphicsView items, editing controls, the main
window and wizard. `app/main.py` is the desktop entry point. Built-in definitions
live in `library/components/`; examples and tests have their own directories.

Components are not hydraulic nodes: each port owns a persistent UUID node.
Connections store instance UUID + port ID at both ends and cross-validated node
UUIDs. Manual visual geometry is separate, under `schematic_geometry`, and is
excluded from logical graph export. Junction ports share internal `JUNCTION`
relationships, preserving the common hydraulic net without extra physical lines.

Project/graph schema version **4** adds definition-level physical data; version 3
introduced manual geometry and required-port metadata. Version 3 loads without
changing its manual geometry; missing physical data defaults to NONE.
Version 1/2 projects migrate deterministically on load. With the authorized
legacy migration, multiple historical lines on a component/external port are
converted into explicit bounded junctions, preserving the net. This happens only
for older file versions; editing never inserts junctions automatically. Opening
does not rewrite the original file; explicit Save writes the current format.

See [format contracts](docs/project-format.md). Unsupported versions and invalid
geometry/occupancy are rejected. Line-click branching remains out of scope.
