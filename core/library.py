import json
import os
from pathlib import Path
from core.component_definition import ComponentDefinition
from core.project import write_json

BUILTINS = Path(__file__).resolve().parents[1] / 'library' / 'components' / 'generic.json'


class ComponentLibrary:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'amcad/components'
        self.definitions = {d.id: d for d in (ComponentDefinition.from_dict(v) for v in json.loads(BUILTINS.read_text()))}
        self.errors = []
        self.paths = {}
        if self.directory.exists():
            for path in sorted(self.directory.glob('*.json')):
                try:
                    definition = ComponentDefinition.from_dict(json.loads(path.read_text(encoding='utf-8')))
                    if definition.id in self.definitions:
                        raise ValueError('Duplicate library definition ID')
                    self.definitions[definition.id] = definition
                    self.paths[definition.id] = path
                except (ValueError, TypeError, KeyError, OSError) as error:
                    self.errors.append(f'{path.name}: {error}')

    def save(self, definition):
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
        definition.validate()
        if not self.is_custom(definition.id):
            raise ValueError('Built-in definitions are templates; save a custom definition instead')
        write_json(self.paths[definition.id],definition.to_dict())
        self.definitions[definition.id]=definition
