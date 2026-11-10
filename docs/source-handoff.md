# Source ZIP handoff

Download GitHub's **main → Code → Download ZIP**, extract the whole folder,
and follow the root README for Python 3.14.4, dependencies, launch and tests.
Git is not needed. Keep `app`, `core`, `ui`, `library`, `examples`,
`integrations`, `docs`, `tests`, requirements files and `.python-version` together.
Personal component/cavity libraries are stored outside this folder; transfer
those separately if needed. Do not include virtual environments, caches or `.git`.

## Local ZIP reconciliation

The supplied `AMCAD-main.zip` matched main at `7924af0`. The supplied
`AMCAD (2).zip` contained updated `topology_core.py`, `topology_ui.py`, and
`examples/c1_r.amcad.json`, plus `topology_diagram.py`, `topology_overview.py`
and an extensionless Python diagnostics module. Those source changes are
preserved here, with the diagnostics module named `topology_diagnostics.py`
so the editor can import it. Other common files differed only in line endings.
Git metadata and generated Python caches were excluded.

The local sample includes a revised cavity profile and interface placement.
Existing exported sample graphs were retained as supplied; regenerate exports
from the project if fresh geometry is required.

## Rhino/Grasshopper limits

Use Rhino 8's Python 3 component and the integration guides. Phase 3/4 `.ghx`
files contain embedded scripts, including machine-specific paths. Change those
paths to the extracted `integrations/grasshopper` directory. Restart Rhino
after replacing Python modules to avoid stale imports.

The recovered editor uses a read-only SVG overview and draft edits published
only on Save. Its additional-port workflow requires a `state['cavities']`
mapping from instance IDs to placed Rhino Breps. The checked-in Phase 4 embedded
topology component does not populate that mapping: adding physical ports needs
native integration work before it is usable there. Existing topology editing
can be reviewed separately. Do not assume the uploaded ZIP contained a newer
Grasshopper definition; its `.ghx` files matched main.

Native Rhino UI, picking, and downstream solver execution require validation in
Rhino; Python-only checks cannot certify them. The optional diagram helper is
retained from the local ZIP even though the current editor uses the SVG helper.
Windows executable packaging remains on `feature/windows-packaging` and is
not part of this source handoff branch.

## Validation for reconciliation

The existing application suite produced **403 passed, 3 failed**. The three
failures also reproduce with the original `7924af0` sample: physical demo
preservation, crossing rendering in `c1_r`, and its historical net topology
expectations. These existing sample/test mismatches remain unresolved.
Three additional topology regression tests passed, covering atomic endpoint
edits, attached-port movement/SVG generation, and draft publication/overwrite
protection. Native Rhino behavior was not tested in this environment.
