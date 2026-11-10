# PyInstaller onedir specification. Build natively on the target OS/architecture.
import os
from pathlib import Path

root=Path(SPECPATH)
datas=[(str(root/'library'/'components'/'generic.json'),'library/components'),
       (str(root/'docs'/'windows-build.md'),'docs')]
# Examples are read-only templates; never seed/overwrite user libraries.
datas += [(str(path),'examples') for path in sorted((root/'examples').glob('*.json'))]

a=Analysis(
    [str(root/'build_support'/'launcher.py')],pathex=[str(root)],
    binaries=[],datas=datas,hiddenimports=[],hookspath=[],hooksconfig={},
    runtime_hooks=[],
    # Export's portable amcad_runtime IS included through normal imports.
    # Rhino-hosted GH UI/importer modules are deliberately not collected.
    excludes=['Rhino','Grasshopper','scriptcontext','Eto','PyQt5','PyQt6','PySide2'],
    noarchive=False,optimize=0,
)
pyz=PYZ(a.pure)
exe=EXE(
    pyz,a.scripts,[],exclude_binaries=True,name='AMCAD',debug=False,
    bootloader_ignore_signals=False,strip=False,upx=False,
    console=os.environ.get('AMCAD_BUILD_CONSOLE')=='1',
    disable_windowed_traceback=False,contents_directory='_internal',
)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='AMCAD')
