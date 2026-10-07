# AMCAD — Hydraulic Manifold Schematic Editor

A standalone Python / PySide6 desktop application for designing hydraulic
schematics and exporting their graph foundation for a future manifold system.
V1 includes a component wizard, an engineering canvas, JSON project persistence,
and hydraulic graph export. It does not implement CAD, simulation, routing or
optimization.

## Setup and run

The target runtime is **Python 3.14.4**, pinned in `.python-version`.
Dependencies are pinned to PySide6 6.11.2 and pytest 9.1.1, which support
Python 3.14. Run commands from the repository root with Python 3.14.4 installed.

```bash
python --version  # Must report Python 3.14.4
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app.main
# Open the included demo:
python -m app.main examples/c1_r.amcad.json
```

For an existing installation, recreate the disposable `.venv` with Python
3.14.4 before installing the updated requirements; upgrading packages alone
does not change the virtual environment's Python runtime. If you use `uv`,
`uv python install 3.14.4` installs the pinned runtime and
`uv venv --python 3.14.4 .venv` creates a new environment.

A normal desktop session is required for interactive use. On Linux, Qt also
needs the platform's display libraries; the pinned PySide6 Linux x86_64 wheels
require glibc 2.34 or newer. For headless CI and cloud validation:

```bash
python -m pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen python -m pytest -q
QT_QPA_PLATFORM=offscreen python -m app.main examples/c1_r.amcad.json --smoke
```

`--smoke` opens and renders the actual application, then exits. It does not
replace the functional tests. The Qt tests exercise the wizard, port clicks,
drag/drop placement, component movement, rotation, properties, editing controls,
project reopening and graph export. All 11 existing tests and the application
launch check pass on Linux with Python 3.14.4, PySide6 6.11.2 and pytest 9.1.1;
the V1 application code and test suite are unchanged. Offscreen validation
cannot establish the behavior of a native Windows/macOS display or executable bundle.

## Editing

- Drag a library component onto the canvas, or double-click the library entry
  to place it at the center of the view.
- Drag component bodies to move them. Click to select; Ctrl-click extends the
  selection and drag an empty area for a selection rectangle.
- Click a hydraulic port, then another port to connect. Press Escape to cancel.
  Selected connections can be deleted independently of components.
- Use **Component → Add Junction** (Ctrl+J) for an explicit branch. Connect every
  branch to its dot. Line crossings do not create connectivity.
- Double-click a component or press F2 for its name, orientation and persistent
  IDs. Rotate selected components with Ctrl+R. Wires remain attached.
- Delete removes selected components and their incident wires, or selected wires.
- Ctrl+C / Ctrl+V copies selected components and the wires between them. Pasted
  objects have fresh IDs and unique names; outside connections are not copied.
  The clipboard is internal to this application session.
- Ctrl+Z / Ctrl+Shift+Z undo/redo schematic edits (up to 100 states). Library
  definition creation is persistent and is not undone with schematic edits.
- Mouse wheel zooms; middle-button drag pans; F fits the schematic.
- File → Save / Open preserves the model, positions and 90-degree orientations.
  File → Export Hydraulic Graph (Ctrl+E) writes a separate JSON netlist.
  Unsaved changes are guarded on New, Open and Close.

Connections are clean orthogonal visualization polylines. They do not perform
obstacle avoidance or hydraulic/physical routing. Endpoint order records the
user's connection order, not simulated flow direction. Unconnected ports are
allowed in V1.

## Component / Node Wizard

Use **+ New Component**. Set name, prefix, category and port count (1–32).
For each port, enter a unique ID, display name, type, flow direction and symbol
side. Row order determines spacing along each side. The preview updates live.

Optionally add internal relationships by naming two of the definition's ports
and a relationship type. These relationships never become routing connections.
This is metadata, not a simulation rule. All future CAD and port geometry fields
are reserved and empty by default.

Custom definitions are saved as JSON beneath:

- Linux/macOS: `$XDG_DATA_HOME/amcad/components`, or `~/.local/share/amcad/components`
- Windows: `~/.local/share/amcad/components` by default; set `XDG_DATA_HOME` to a
  preferred writable data directory if desired.

Project files embed their definitions and do not depend on the original library
files. Opening a project also makes its embedded definitions available in the
library panel for that project. A malformed custom library file is reported in
the status bar and does not prevent loading valid definitions.

## C1–R acceptance walkthrough

1. Create **EHSV**, prefix **EHSV**, category **Valves**, with four ports:
   P (TOP), R (BOTTOM), C1 (LEFT), C2 (RIGHT).
2. Create **Relief Valve**, prefix **RV**, with IN (LEFT, IN) and OUT (RIGHT, OUT).
   Add internal relationship `IN → OUT`, type `RELIEF_VALVE`.
3. Place two External Ports; rename them **C1** and **R**. Place EHSV1, RV1 and J1.
4. Connect C1.port ↔ J1.j, J1.j ↔ EHSV1.C1, J1.j ↔ RV1.IN,
   RV1.OUT ↔ R.port, and EHSV1.R ↔ R.port.
5. Move and rotate RV1, then save, close, reopen and export the graph.

The supplied [sample project](examples/c1_r.amcad.json) and
[exported graph](examples/c1_r.graph.json) demonstrate this architecture.
The export has **5 instances, 9 hydraulic nodes, 1 junction, 5 routing
connections and 1 component-internal relationship**. EHSV.P and EHSV.C2 remain
unconnected intentionally. Regenerate examples with `python -m examples.create_demo`.

## Architecture and data contracts

- `core/`: pure Python definitions, instances, nodes, connections, project
  validation/persistence, history, component library and graph export. No Qt imports.
- `ui/`: QGraphicsScene / QGraphicsView rendering and interactions, main window,
  component library panel and wizard. GUI edits operate on the core graph.
- `app/main.py`: desktop entry point.
- `library/components/`: the four generic built-in definitions only.
- `examples/`: C1–R sample and exported netlist.
- `tests/`: core integrity and Qt functional acceptance tests.

A component is not a hydraulic node. Every component port owns a separate UUID
node. External ports and junctions each own one node. Wires refer only to node
UUIDs, never coordinates or visible names. Definition port IDs remain fixed
within that definition. Renaming an instance changes labels without changing
connectivity. Internal relationships belong to definitions and are expanded
into their instance port-node IDs only at graph export.

See [project and graph formats](docs/project-format.md) for the versioned JSON
contracts. Future migrations must be explicit; unsupported schema versions are
rejected instead of silently interpreted.
