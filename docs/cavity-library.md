# V1.5 independent cavity library and instance assignment

A schematic Component Definition owns its symbol, ports and internal relationships.
A Component Instance owns its `cavity_ref` and explicit `port_mapping`. A standalone
Cavity Definition owns its profile and hydraulic interfaces. Connecting instances
never changes or creates cavity sharing. Geometry is edited through Cavity Library,
using the existing four-view editor. New component definitions have no embedded cavity.

## Storage and identities

Cavity JSON records use `schema: amcad.cavity`, `schema_version: 1`, `id`, `name`,
`revision`, `geometry_type`, `profile`, `interfaces`, and optional `description`.
New cavities start at revision 1. The `port_count` index is derived from interfaces;
it is checked when reading and is never user-entered. Save retains the ID and increments
revision only when content changes. Save As New / Duplicate create a new cavity ID,
profile/vertex IDs and interface IDs; surface anchors are remapped to the copied vertices.
All numeric geometry, treatments, directions, sections and previews are preserved.
Copies do not share mutable data. Old revision objects cannot overwrite newer library data.

Interface identity is the persistent `HydraulicInterface.id`, independent of schematic
names. The retained serializer field `hydraulic_port_id` equals that same interface ID
inside independent cavities; it is not a schematic port association. Interface labels
are shown as Interface 1, Interface 2, etc.; these display indices are not identifiers.
The editor generates new interface IDs when a surface is picked and derives the count.
Legacy schematic-name fields remain readable in archived embedded component data.

Configure storage with `AMCAD_CAVITY_LIBRARY`, or pass `cavity_library_directory` to
MainWindow / a directory to CavityLibrary. Defaults are:

- Linux: `$XDG_DATA_HOME/amcad/cavities`, or `~/.local/share/amcad/cavities`.
- Windows: `%LOCALAPPDATA%/amcad/cavities`.
- macOS: `~/Library/Application Support/amcad/cavities`.

When an explicit component library directory is supplied to MainWindow without a
cavity directory, cavities use its sibling `cavities` directory. The manager displays
the effective path. Generated UUID filenames avoid interpreting cavity names as paths.
Writes replace JSON atomically. Malformed or duplicate records appear as load errors.
No database or source-directory write permission is needed.

## Actions and mapping

Cavity → New Cavity works without a selected component. Save requires a nonempty name,
valid revolved profile and valid anchors for all interfaces. The existing profile,
corner, axis-lock, picking, quaternion camera and preview behavior remains available.
Cavity → Cavity Library displays name, count, geometry type, revision, open-project
usage and library/snapshot status. It offers New, Open/Edit, Duplicate, Rename, Delete,
Assign, Remove Assignment, Open Assigned Cavity, and Refresh Project Snapshot.
Delete is refused when the open project uses that ID. Shared editing names the affected
instances before Save; removing interfaces needed by existing mappings is rejected
before either the library or snapshots change. Save As New leaves existing assignments
unchanged until the user explicitly assigns the new copy.

Select an instance and choose Component → Assign Cavity (Ctrl+Shift+C), or double-click
it and use Assign Cavity in Properties. Compatible filtering requires matching interface
count and valid geometry/anchors. One-port mapping is unambiguous; multi-port mappings
start unselected and require explicit choices. Every schematic port must map to exactly
one interface, and each interface must be used once. No name matching or interface-order
heuristic guesses the mapping. Optional schematic ports also participate in this mapping.

## Project portability and revision status

Project and hydraulic graph schema 6 add `cavity_definitions` snapshots and instance
`cavity_ref` / `port_mapping`. Versions 1–5 still load; profile schema stays at 1.
References require sufficient snapshots and valid complete mappings when loading/saving.
Copy/paste includes the relevant snapshots and mappings. Paste into an existing project
uses its current snapshot for a known ID and rejects incompatible mappings transactionally.
Assignment, removal and shared snapshot edits participate in project undo/redo.
Library writes remain independent of project history: undo does not undo persistent
library edits, so a revision mismatch may appear afterward.

Loading a project never writes to the library. A missing library ID uses its saved
snapshot and remains editable as a copy through Save As New. A differing library record
shows both revision numbers and requires explicit Refresh Project Snapshot or library
editing. Existing instance mappings are checked before any refresh. An older project
snapshot never silently overwrites a library definition. Saving a snapshot whose primary
library ID is missing requires Save As New; the old project reference remains intact.

## Explicit legacy migration

Legacy `ComponentDefinition.physical` remains preserved for compatibility, as archived
embedded data. It is not edited by the new component wizard or definition actions.
Loading an old file leaves connectivity, instance IDs and geometry unchanged and does
not assume permanent sharing. Assignment Properties / the library manager exposes
Import Legacy for This Instance when such data exists.

Import creates a per-instance cavity ID derived from project ID, instance ID and a digest
of the legacy physical data. Interface IDs are deterministic within that cavity. Repeating
an import reuses the existing record, including user edits; other instances import their
own independent cavities. The user may later explicitly choose to share one definition.
Original theoretical profile IDs, coordinates, corner features, sections and previews
are preserved. An exact known surface location can supply a legacy marker anchor without
moving it. Unknown axis azimuth or off-surface locations remain unresolved, never snapped.
Legacy off-axis profiles and unanchored interfaces import as clearly invalid library
records for repair. These drafts can be renamed or duplicated while retaining their
invalid status. They cannot be assigned until the editor's explicit endpoint correction
and surface reattachment produce valid geometry. Import does not auto-assign or delete
the archived embedded data. After repair, mapping is chosen explicitly.

## Manual verification

1. Start AMCAD, place External Port twice, and rename the instances R and RET.
2. Open Cavity → New Cavity without selecting a component. Draw a valid axis-closed
   profile, pick one surface interface, name it CAVITY_A and Save. Repeat for CAVITY_B.
3. Open the library and inspect count/revision/usage; duplicate a cavity and inspect
   its independent ID and interfaces. Resize/maximize the existing editor.
4. Assign CAVITY_A to R and CAVITY_B to RET through Properties. Verify distinct refs.
5. Replace RET's assignment with CAVITY_A. Open it for editing, read the shared-use
   warning, Save a change, and verify both instances still reference that ID.
6. Save As New to make an independent copy; verify the original and assignments stay
   intact. Remove one assignment, then check that deleting a still-used cavity fails.
7. Save the project and reopen it with another empty library directory. Verify snapshot
   status, geometry and mappings; use Save As New to create a library copy explicitly.
8. Open an old check-valve project, import for just CV1, repeat the import, and verify no
   duplicates or automatic assignments. Repair the imported profile/anchors before mapping.

The portable `examples/instance_cavities.amcad.json` demonstrates connected R/RET instances
with different cavities. Its snapshots open without installing a library. Use Save As New
and explicit replacement to bring them into your library.

## Limits

No immutable revision history, live filesystem watching or reconciliation of concurrent
library edits is implemented. Delete protects the open project; other projects remain
portable through snapshots and report a missing primary record after deletion. Migration
is explicit per instance, not a bulk auto-conversion. No CAD Boolean, Rhino, surface trimming,
automatic placement, routing or CFD is included. Rendering and intersection validation
retain the existing visualization tessellation limits.
