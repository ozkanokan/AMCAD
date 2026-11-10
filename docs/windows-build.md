# Windows onedir build — AMCAD V1.6a

## Build (Windows 10/11 x64)

Install **64-bit CPython 3.14.4** on the build PC. The runtime PySide6 version remains **6.11.2**. From the project root:

```bat
build_exe.bat
```

The script works from another current directory too. It uses `py -3.14`, verifies exact Python version and architecture, creates a separate `.venv-build`, installs the pinned `requirements-build.txt`, and runs `AMCAD.spec`. To select a Python executable explicitly:

```bat
set "AMCAD_BUILD_PYTHON=C:\Path With Spaces\Python314\python.exe"
build_exe.bat
```

For a diagnostic console build, run `build_exe.bat --console`. The normal build is windowed. Both builds replace the generated `dist\AMCAD` output, never projects or user libraries. Do not keep editable user data in build/dist directories. Build-environment versions are recorded in `build\AMCAD\build-environment.txt`. `build\AMCAD\warn-AMCAD.txt` contains PyInstaller's import analysis; OS-specific optional imports can be harmless, but application/Qt missing imports must be investigated.

The checked-in spec intentionally builds **onedir**, without UPX or stripping:

```text
dist\AMCAD\AMCAD.exe
dist\AMCAD\_internal\...
```

Copy the **entire `dist\AMCAD` folder**, not just the EXE. Python and Rhino are not required on the receiving PC. Do not mix files from different builds. PyInstaller is not a Windows cross-compiler: a Linux build of this spec produces a Linux executable, not an EXE. A Windows build must be generated and accepted on Windows.

## Resources and writable data

- `library/components/generic.json` is bundled at its existing relative location. The existing `Path(__file__)` lookup works in source and in PyInstaller's `_internal` directory; no resource/data schema changes are needed.
- Five example projects plus their JSON companion files are bundled as read-only templates in `_internal/examples`. Copy a template into Documents before editing it, or use Save As. Do not edit the distribution's resources.
- All icons/previews are drawn in Qt; no external image/font resource directory is required by the current app.
- The pure-Python `integrations.grasshopper.amcad_runtime` export validator is included through normal import analysis. Rhino importers, GH Python component scripts and Eto integrations are not collected. No Rhino installation dependency is added.
- PyInstaller's PySide6 hooks collect Qt libraries and platform plugins (including `qwindows.dll` on Windows). `check_distribution.py` verifies the EXE, catalogue and platform plugin after building.
- Existing editable libraries remain `%LOCALAPPDATA%\amcad\components` and `%LOCALAPPDATA%\amcad\cavities`. Existing `AMCAD_COMPONENT_LIBRARY` / `AMCAD_CAVITY_LIBRARY` overrides still work. Use absolute, writable paths for overrides. Existing library data is not seeded, migrated or overwritten by installing/updating the distribution.
- **Frozen launches only** start in the user's Documents/AMCAD folder (created if absent), so new project/export dialogs use a writable default instead of the installation folder. Existing caller-relative CLI project arguments are resolved before that change. Source launches keep their existing working directory.
- Optional `AMCAD_DOCUMENTS_DIR` overrides the frozen default directory, useful for managed locations or isolated testing. Explicitly chosen project/export destinations remain under user control; choosing an unwritable destination reports the existing file-I/O error rather than silently redirecting or changing it.

## Acceptance on the build PC and a second PC

1. Run the normal build and the post-build structural check. Launch `dist\AMCAD\AMCAD.exe` from Explorer, then from a different working directory. Verify the main window and both libraries appear.
2. Create/drag/connect components, open the component wizard and cavity editor, and exercise undo/redo. Save a project under Documents, close/reopen it, export the hydraulic graph and Grasshopper JSON. Check data with the existing Rhino/GH importer if available; Rhino is **not** needed to export.
3. Create a custom component/cavity, restart AMCAD and verify the objects persist under LocalAppData. Verify no new user files appear under `_internal` or the installation directory. Do not delete existing libraries to test this; use the overrides for isolation if desired.
4. Copy the complete distribution to a Windows x64 PC with **no Python, development checkout or Rhino installed**, preferably under a standard non-writable installation location. Repeat steps 1–3 as a normal user. This is the required native independence check.
5. If Qt fails to start, use the console build and `set QT_DEBUG_PLUGINS=1`, then run the EXE from a terminal. Verify the entire `_internal` tree was copied, especially `platforms/qwindows.dll`. Do not install PySide6 on the target PC as a workaround for a missing bundle dependency.

### Automated check inside the frozen EXE (no target Python needed)

A packaging-only environment variable enables an isolated acceptance check inside the actual executable. It creates a new directory per run, renders all five examples, saves/reloads a project, exports/validates both JSON formats, and writes/reloads custom component/cavity library objects. It never touches normal user libraries or existing sample files.

PowerShell:

```powershell
$testRoot = Join-Path $env:TEMP ('AMCAD-acceptance-' + [guid]::NewGuid())
$env:AMCAD_PACKAGING_SMOKE_DIR = $testRoot
$env:AMCAD_DOCUMENTS_DIR = Join-Path $testRoot 'Documents'
$p = Start-Process '.\dist\AMCAD\AMCAD.exe' -Wait -PassThru
$p.ExitCode
Get-ChildItem $testRoot -Recurse -Filter result.json | Get-Content
Remove-Item Env:AMCAD_PACKAGING_SMOKE_DIR
Remove-Item Env:AMCAD_DOCUMENTS_DIR
```

Expect exit code **0**, `ok: true`, `frozen: true`, platform `windows`, and every listed check. A nonzero exit/result error needs investigation. Keep the test artifacts for review; removal of the test directory is optional. Also run a normal interactive launch with the test variables removed. The check is diagnostic packaging support, not a new UI/export feature.

## Linux/cloud validation limits

The same spec can be built on Linux to test import collection, bundled resources, Qt offscreen rendering, library persistence and export execution inside a frozen binary. This is useful evidence but **does not validate `build_exe.bat`, a Windows PE executable, `qwindows.dll` loading, Windows dialogs, antivirus behavior, or independence on another Windows PC**. Those remain the native acceptance steps above.

## Validation performed for this change

- Source application launch/render/exit passed on Python 3.14.4 / PySide6 6.11.2.
- PyInstaller 6.22.3 / hooks 2026.9 successfully built this exact onedir spec on Linux. The platform plugin and built-in resource structural check passed.
- The acceptance check ran successfully **inside the frozen executable**: all five examples rendered; project save/load, graph export, nonempty Grasshopper export validation and both editable library round trips passed. The bundled archive contains the portable export validator and no Rhino-hosted UI/importer modules.
- The whole distribution was copied into a differently named folder containing spaces, made read-only, and launched from an unrelated working directory with a minimal environment (no Python/Qt development path overrides). The frozen acceptance check passed; reported application module/resource/Qt plugin locations were all inside the relocated bundle.
- Normal `--smoke` launch also passed using the uploaded ZIP's project through a caller-relative filename containing spaces, after the frozen launcher changed to its writable working directory.
- Seven packaging-specific tests passed. Full repository suite: **410 passed, 3 failed**. The failures are the existing `c1_r` example expectation mismatches in `test_physical_demo_launch_graph_and_existing_c1_r_preserved`, `test_crossings_are_render_only_deterministic_and_survive_sample_reopen`, and `test_sample_net_topology_and_legacy_migration_required_defaults`. Those tests, sample files and application code were not modified for packaging.

**Not performed:** Windows batch execution, Windows EXE generation, native `qwindows.dll` loading, interactive Windows dialogs, or testing on a second Windows PC without Python/Rhino. Complete those before calling the Windows distribution validated. The Linux executable is evidence for bundle completeness, not a distributable Windows artifact.
