# V1.6 libraries and schematic workflow

Both libraries are tabbed docks by default; drag their titles to float or dock
elsewhere. View → Component Library / Cavity Library controls visibility. Closing
a dock hides it and does not delete definitions. The toolbar contains Save,
Undo, Redo, Delete Selection and Fit Schematic. Instance context menus retain
Properties, Rotate, Assign Cavity, Remove Assignment and Save as Library Component.
Ctrl+R and F2 remain available. Junctions remain in the Component Library.

## Components and categories

Drag or double-click N-Port Generic and select a count between 1 and 128. Existing
generic templates default to Port 1, Port 2, etc.; old saved definitions retain
their labels. Properties edits display labels and Left/Right/Top/Bottom edges for
all component types. Ports distribute evenly per edge. IDs, connections and cavity
mappings remain stable. Junction edges must remain distinct. Count changes are
instance-specific; connected ports cannot be removed, and assigned cavities must
be removed before changing the count.

Component → Component Library provides New, Save Selected Instance, Edit, Rename,
Delete, New Category, Rename / Move Category and Move Entry. Nested paths such as
`Lee/Check Valves` become collapsible branches in the library dock. Saved instances
retain their effective labels and edge layout. The optional cavity default stores
only its cavity ID and complete port mapping. Future placements resolve that ID
from the independent Cavity Library and can change/remove the assignment individually.
A missing, invalid or incompatible default places the component unassigned with a
status message. Library edits increment revisions without changing placed snapshots;
a new revision placed alongside an older one receives its own project definition.

Both managers support category organization. Cavity category changes write only
`categories.json`, preserving cavity file bytes, geometry, IDs and revisions.
Symbol previews render actual schematic items; cavity previews render the evaluated
YZ profile with true corner geometry, proportional fit and no editor overlays.

## Cavity assignment and usage

Properties → Assign Cavity shows matching valid cavities and selects the current
assignment when reopened. Every port count, including one, requires an explicit
mapping. Rows use current instance labels and readable Interface 1, Interface 2,
etc. A complete unique mapping closes the assignment manager automatically and
refreshes Properties. Accepting Properties retains the latest assignment.
Remove Cavity Assignment clears only the instance reference/mapping.

The library manager lists usage counts and referencing instance names. Select a
reference to Locate in Schematic or Remove Selected Reference, which requires
confirmation. The cavity dock's In Use section shows names/counts and offers
Locate; shared cavities prompt for the instance. Used cavities cannot be deleted.
Assignment changes mark the project dirty; saving remains explicit. Library file
writes are independent of project undo/redo, while instance assignments and port
configuration are included in project history.

## Local verification

Use Python **3.14.4** and install `requirements-dev.txt`. For an isolated review,
point both libraries at disposable directories before launching:

```bash
export AMCAD_COMPONENT_LIBRARY=/tmp/amcad-v16-review/components
export AMCAD_CAVITY_LIBRARY=/tmp/amcad-v16-review/cavities
python -m app.main examples/instance_cavities.amcad.json
```

On Windows PowerShell, set `$env:AMCAD_COMPONENT_LIBRARY` and
`$env:AMCAD_CAVITY_LIBRARY` to two folders beneath a disposable `$env:TEMP` review
folder. These overrides do not copy, reset or modify the normal AppData libraries.

1. Toggle both docks using View and each dock's close control.
2. Place N-Port Generic components with 1, 2, 5 and 20 ports. Rename labels and
   move ports to all four edges in Properties. Confirm the other instance is unchanged.
3. Connect a port, rename/reposition/rotate it, and verify its line remains attached.
4. Save a selected component to the library. Reopen the app in another project and
   drag the saved symbol in. Edit its library revision and confirm existing placements
   stay unchanged. Create nested categories and move entries.
5. Open the independent cavity manager and create/save a valid one-port cavity.
   Assign it explicitly to a one-port component, then repeat for another instance.
   Confirm Properties updates immediately. Save a reusable component with cavity defaults.
6. Check usage names/counts, locate either reference, remove one with confirmation,
   and confirm the cavity remains available. Reopen assignment and confirm selection.
7. Drag components near port and center alignments at several zoom levels and after
   rotation. Guides disappear on release; arbitrary off-grid placement remains possible.
8. Save/reopen the project; check labels, IDs, connections, mappings and cavity geometry.

Automated checks, all using temporary library directories:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
QT_QPA_PLATFORM=offscreen python -m app.main examples/instance_cavities.amcad.json --smoke
```

Native Windows/macOS rendering is not covered by the Linux headless checks.
Alignment assistance applies to individual drags; multi-selection drags retain
Qt's rigid relative placement without magnetic snapping. No free-coordinate port
editing, Rhino integration, channel routing or additional physical geometry is added.
