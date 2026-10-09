import json
import os
from pathlib import Path
from core.component_definition import ComponentDefinition
from core.project import write_json

BUILTINS = Path(__file__).resolve().parents[1] / 'library' / 'components' / 'generic.json'


from copy import deepcopy
from core.library_categories import LibraryCategories


class ComponentLibrary(LibraryCategories):
    def __init__(self, directory=None):
        from core.cavity_library import default_cavity_directory
        self.directory=Path(directory) if directory is not None else Path(os.environ['AMCAD_COMPONENT_LIBRARY']).expanduser() if os.environ.get('AMCAD_COMPONENT_LIBRARY') else default_cavity_directory().parent/'components'
        self.definitions = {d.id: d for d in (ComponentDefinition.from_dict(v) for v in json.loads(BUILTINS.read_text()))}
        self.errors = []
        self.paths = {}
        if self.directory.exists():
            for path in sorted(self.directory.glob('*.json')):
                if path.name=='categories.json':continue
                try:
                    definition = ComponentDefinition.from_dict(json.loads(path.read_text(encoding='utf-8')))
                    if definition.id in self.definitions:
                        raise ValueError('Duplicate library definition ID')
                    self.definitions[definition.id] = definition
                    self.paths[definition.id] = path
                except (ValueError, TypeError, KeyError, OSError) as error:
                    self.errors.append(f'{path.name}: {error}')

        self.load_categories()

    def save(self, definition):
        definition=deepcopy(definition)
        definition.validate()
        if definition.id in self.definitions:
            raise ValueError('Definition ID already exists')
        self.directory.mkdir(parents=True, exist_ok=True)
        # Generated UUID filename, never a user-supplied name or path.
        from core.port import new_id
        path=self.directory / f'{new_id()}.json'
        write_json(path, definition.to_dict())
        self.paths[definition.id]=path
        self.definitions[definition.id] = definition

    def is_custom(self, definition_id):
        return definition_id in self.paths

    def update(self, definition):
        definition=deepcopy(definition)
        definition.validate()
        if not self.is_custom(definition.id):
            raise ValueError('Built-in definitions are templates; save a custom definition instead')
        old=self.definitions[definition.id]
        if definition.revision!=old.revision:raise ValueError("Component revision changed; reopen before saving")
        if definition==old:return deepcopy(old)
        definition.revision+=1
        write_json(self.paths[definition.id],definition.to_dict())
        self.definitions[definition.id]=definition

    def delete(self,definition_id,project):
        if not self.is_custom(definition_id):raise ValueError('Built-in templates cannot be deleted')
        if any(i.definition_id==definition_id for i in project.instances.values()):raise ValueError('Component is used by the open project')
        self.paths[definition_id].unlink();del self.paths[definition_id];del self.definitions[definition_id]
