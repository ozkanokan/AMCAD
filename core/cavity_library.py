"""Atomic independent cavity library; project snapshots never overwrite it implicitly."""
import json
import os
import sys
from pathlib import Path
from copy import deepcopy
from core.cavity_definition import CavityDefinition
from core.project import write_json
from core.port import new_id


def default_cavity_directory():
    if os.environ.get('AMCAD_CAVITY_LIBRARY'):return Path(os.environ['AMCAD_CAVITY_LIBRARY']).expanduser()
    if sys.platform=='win32':base=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))
    elif sys.platform=='darwin':base=Path.home()/'Library/Application Support'
    else:base=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))
    return base/'amcad/cavities'


from core.library_categories import LibraryCategories


class CavityLibrary(LibraryCategories):
    def __init__(self,directory=None):
        self.directory=Path(directory) if directory is not None else default_cavity_directory()
        self.definitions={};self.paths={};self.errors=[]
        if self.directory.exists():
            for path in sorted(self.directory.glob('*.json')):
                if path.name=='categories.json':continue
                try:
                    cavity=CavityDefinition.from_dict(json.loads(path.read_text(encoding='utf-8')))
                    if cavity.id in self.definitions:raise ValueError('Duplicate cavity ID')
                    self.definitions[cavity.id]=cavity;self.paths[cavity.id]=path
                except (ValueError,TypeError,KeyError,OSError) as error:self.errors.append(f'{path.name}: {error}')

        self.load_categories()

    def save(self,cavity,allow_legacy=False):
        cavity=deepcopy(cavity).validate(strict=not allow_legacy)
        if cavity.id in self.definitions:
            old=self.definitions[cavity.id]
            if cavity.revision!=old.revision:raise ValueError('Library revision changed; reopen the current cavity before saving')
            if cavity.to_dict()==old.to_dict():return deepcopy(old)
            cavity.revision=old.revision+1
            path=self.paths[cavity.id]
        else:
            if cavity.revision!=1:raise ValueError('New cavities start at revision 1; use Save As New for a snapshot')
            path=self.directory/f'{new_id()}.json'
        self.directory.mkdir(parents=True,exist_ok=True)
        write_json(path,cavity.to_dict());self.paths[cavity.id]=path;self.definitions[cavity.id]=deepcopy(cavity)
        return deepcopy(cavity)

    def import_legacy(self,project,instance_id):
        from core.cavity_definition import legacy_cavity
        cavity,mapping=legacy_cavity(project,instance_id)
        # Repeated imports reuse the existing object, including intentional user edits.
        if cavity.id not in self.definitions:self.save(cavity,allow_legacy=True)
        return deepcopy(self.definitions[cavity.id]),mapping

    def delete(self,cavity_id,project):
        if project.cavity_usage(cavity_id):raise ValueError('Cavity is used by the open project; remove or replace those assignments first')
        self.paths[cavity_id].unlink();del self.paths[cavity_id];del self.definitions[cavity_id]

    def status(self,project,cavity_id):
        current=self.definitions.get(cavity_id);snapshot=project.cavities.get(cavity_id)
        if current is None:return 'Missing library reference — using project snapshot'
        if snapshot is not None and current.to_dict()!=snapshot.to_dict():
            return f'Library revision {current.revision}; project snapshot revision {snapshot.revision} — explicit refresh required'
        return 'Library available'
