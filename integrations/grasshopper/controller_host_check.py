"""Run in Rhino 8 ScriptEditor Python 3; tests real Eto events using temp data."""
import sys
import tempfile
from pathlib import Path
folder=Path(__file__).resolve().parent
if str(folder) not in sys.path:sys.path.insert(0,str(folder))
import amcad_runtime as runtime
from placement_controller import PlacementController
from placement_editor import PlacementEditor,show_editor
from rhino_importer import import_model

review=tempfile.TemporaryDirectory(prefix='amcad-controller-review-')
path=Path(review.name)/'placements.json'
data=runtime.load_export(folder/'phase2-seven.grasshopper.json')
stored=runtime.load_placements(folder/'phase2-seven.placements.json',data['project']['id'])
model=PlacementController(data,path,stored=stored)
window=PlacementEditor(model,lambda:None,lambda form:review.cleanup())
window._review_directory=review
records=model.catalog();a=next(r['id'] for r in records if r['name']=='CV1');b=next(r['id'] for r in records if r['name']=='CV2')
# Native ListBox changes invoke the real selection handler and populate the six fields.
window.instances.SelectedIndex=next(i for i,r in enumerate(window._records) if r['id']==a)
window.fields[0].Text='50';window.apply(None,None)
window.instances.SelectedIndex=next(i for i,r in enumerate(window._records) if r['id']==b)
assert window.fields[0].Text=='25'  # B loads its own original pose, never A's 50.
window.fields[1].Text='30';window.apply(None,None)
window.instances.SelectedIndex=next(i for i,r in enumerate(window._records) if r['id']==a)
assert float(window.fields[0].Text)==50 and model.placement(b)['translation_mm'][1]==30
window.save(None,None)
assert path.is_file()
reopened=PlacementController(data,path);assert reopened.snapshot()==model.snapshot()
models=import_model(data,reopened.snapshot())
assert len(models)==7 and all(m['geometry'].IsValid and m['geometry'].IsSolid for m in models)
print('PASS: native Eto selection/apply, seven-instance persistence and Phase 1 Rhino geometry.')
show_editor(window)
print('A review editor is open; its temporary placement data is removed when it closes.')
