"""Opt-in packaging acceptance check, executed INSIDE the frozen application.

AMCAD_PACKAGING_SMOKE_DIR must name a writable test root. Every run creates a
new subdirectory. No existing project or normal user library is modified.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback


def run(output_directory):
    output_directory=Path(output_directory);output_directory.mkdir(parents=True,exist_ok=True)
    output=Path(tempfile.mkdtemp(prefix='amcad-package-',dir=output_directory))
    os.environ['AMCAD_COMPONENT_LIBRARY']=str(output/'components')
    os.environ['AMCAD_CAVITY_LIBRARY']=str(output/'cavities')
    report={'ok':False,'frozen':bool(getattr(sys,'frozen',False)),
            'executable':sys.executable,'output':str(output),'checks':[]}
    window=None;code=1
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer,QLibraryInfo
        from core.library import ComponentLibrary,BUILTINS
        from core.cavity_library import CavityLibrary
        from core.cavity_definition import CavityDefinition
        from core.cavity import CavityProfile,ProfileVertex
        from core.project import Project
        from core.graph import export_graph
        from core.port import new_id
        from ui.main_window import MainWindow
        from integrations.grasshopper.amcad_runtime import validate_export
        from copy import deepcopy
        app=QApplication.instance() or QApplication([sys.executable])
        app.setApplicationName('AMCAD');app.setStyle('Fusion')
        report.update(platform_plugin=app.platformName(),qt_plugin_paths=app.libraryPaths(),
                      qt_plugin_location=QLibraryInfo.path(QLibraryInfo.PluginsPath),builtins=str(BUILTINS))
        bundle=Path(sys._MEIPASS) if report['frozen'] else Path(__file__).resolve().parents[1]
        window=MainWindow();window.show();app.processEvents()
        assert window.library.definitions,'Built-in definitions missing'
        assert window.library.directory==output/'components'
        assert window.cavity_library.directory==output/'cavities'
        assert not window.grab().isNull(),'Window rendering failed'
        report['checks'].append('Qt platform plugin, main window, built-ins, default writable library configuration')
        samples=('c1_r.amcad.json','parallel_check_valves.amcad.json',
                 'parallel_check_valves_3d.amcad.json','parallel_check_valves_v14a.amcad.json',
                 'instance_cavities.amcad.json')
        for name in samples:
            window.load_path(bundle/'examples'/name);app.processEvents()
            assert not window.grab().isNull()
        report['checks'].append('All five bundled example projects load and render')
        window.save_to(output/'project.amcad.json')
        loaded=Project.load(output/'project.amcad.json')
        assert loaded.to_dict()==window.project.to_dict()
        window.export_to(output/'hydraulic.graph.json')
        assert json.loads((output/'hydraulic.graph.json').read_text())==export_graph(loaded)
        window.export_grasshopper_to(output/'project.grasshopper.json')
        handoff=json.loads((output/'project.grasshopper.json').read_text())
        validate_export(handoff)
        assert handoff['instances'] and handoff['cavities'],'Physical export was empty'
        report['checks'].append('Project save/load, hydraulic graph and nonempty Grasshopper export round trips')
        definition=deepcopy(next(iter(window.library.definitions.values())))
        definition.id=new_id();definition.name='Packaging smoke component'
        window.library.save(definition)
        assert ComponentLibrary().definitions[definition.id]==definition
        cavity=CavityDefinition('Packaging smoke cavity',CavityProfile([ProfileVertex(*p) for p in [(0,0),(0,4),(8,4),(8,0)]]),[])
        saved=window.cavity_library.save(cavity)
        assert CavityLibrary().definitions[saved.id].to_dict()==saved.to_dict()
        report['checks'].append('Editable component and cavity library persistence/reload')
        assert not {'Rhino','Grasshopper','scriptcontext','Eto'}.intersection(sys.modules)
        report['module_locations']={name:str(sys.modules[name].__file__) for name in
            ('core.project','ui.main_window','integrations.grasshopper.amcad_runtime')}
        if report['frozen']:
            assert all(Path(path).is_relative_to(bundle) for path in report['module_locations'].values())
        report['checks'].append('No Rhino/Grasshopper/Eto host dependency imported')
        # Exercise an actual event-loop iteration, including deferred Qt work.
        QTimer.singleShot(100,app.quit);app.exec()
        report['ok']=True;code=0
    except Exception:
        report['error']=traceback.format_exc()
    finally:
        if window is not None:window.close()
        (output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return code
