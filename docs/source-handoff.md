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
The hydraulic graph for `c1_r` has since been regenerated from the current
project using the existing exporter. See the root README for its current topology.

## Rhino/Grasshopper limits

Use Rhino 8's Python 3 component and the integration guides. Phase 3/4 `.ghx`
files contain embedded scripts, including machine-specific paths. Change those
paths to the extracted `integrations/grasshopper` directory. Restart Rhino
after replacing Python modules to avoid stale imports.

The recovered downstream editor uses a read-only SVG overview and draft edits
published only on Save. Its additional-port workflow expects a runtime
`state['cavities']` mapping from instance IDs to placed Rhino Breps; the included
Phase 4 component's state initializer omits that key. This is a static observation
about that component/module combination, not an AMCAD assignment/export defect
or a reproduced failure of the user's working Rhino session. The uploaded ZIP's
`.ghx` files matched main. Downstream runtime investigation is outside AMCAD's
standalone design-to-JSON responsibility.

Native Rhino UI, picking, and downstream solver execution require validation in
Rhino; Python-only checks cannot certify them. The optional diagram helper is
retained from the local ZIP even though the current editor uses the SVG helper.
Windows executable packaging remains on `feature/windows-packaging` and is
not part of this source handoff branch.

## Validation for source handoff

The complete suite passed **409 tests**, including the three topology tests
added during ZIP reconciliation. The former three sample-expectation failures
are corrected without changing application behavior: the historical generator
still exercises crossings and legacy topology; the current sample has explicit
topology, preservation, export and round-trip checks. The shipped `c1_r` graph
matches the current project. All seven sample projects passed save/load and
export round trips and offscreen application launches. All five stored hydraulic
graphs match their source projects, and both stored Grasshopper exports match
their source project/generator; associated placement JSON also validates.
Native Rhino behavior is outside this validation.

Keep the editable project alongside exports. The three JSON contracts and
existing incomplete-design/physical-exclusion behavior are documented in
[project-format.md](project-format.md#export-boundary-and-contract-selection).
