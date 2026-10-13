"""UI-independent, stable-ID placement state for Rhino/GH and future algorithms.

Python 3.9+. Uses the Phase 1 schema and transform/persistence implementation.
"""
from copy import deepcopy
from pathlib import Path
from threading import RLock
import re
try:
    from . import amcad_runtime as runtime
except ImportError:
    import amcad_runtime as runtime


class PlacementController:
    def __init__(self,export,placement_path=None,export_path=None,stored=None):
        runtime.validate_export(export)
        self._lock=RLock();self.placement_path=str(placement_path) if placement_path else None
        self.export_path=str(export_path) if export_path else None
        saved=deepcopy(stored) if stored is not None else runtime.load_placements(self.placement_path,export['project']['id'])
        self._validate_state(saved,export['project']['id'])
        self._saved=deepcopy(saved);self._state=runtime.reconcile_placements(export,saved)
        self._export=deepcopy(export);self._selected=None;self._generation=0
        self.export_version=0;self.state_version=0

    @staticmethod
    def _validate_state(state,project_id):
        runtime.require(isinstance(state,dict) and state.get('schema')=='amcad.placements' and type(state.get('schema_version')) is int and state['schema_version']==1 and state.get('units')=='mm','Unsupported placement schema/units')
        runtime.require(state.get('project_id')==project_id,'Placement project mismatch')
        runtime.require(isinstance(state.get('placements'),dict),'Invalid placement collection')
        for key,value in state['placements'].items():
            runtime.identifier(key,'Placement instance')
            runtime.require(isinstance(value,dict) and 'translation_mm' in value and 'rotation_deg' in value,'Invalid placement record')
            runtime.pose(value['translation_mm'],value['rotation_deg'])

    @property
    def selected_id(self):
        with self._lock:return self._selected

    @property
    def selection_token(self):
        with self._lock:return self._selected,self._generation

    @property
    def dirty(self):
        with self._lock:return self._state!=self._saved

    @property
    def version(self):
        with self._lock:return self.export_version,self.state_version

    def catalog(self,query=''):
        with self._lock:
            records=[{'id':i['id'],'name':i['name'],'cavity_id':i['cavity_id']} for i in self._export['instances']]
        for record in records:runtime.identifier(record['name'],'Instance name')
        def key(record):return [int(s) if s.isdigit() else s for s in re.split(r'(\d+)',record['name'].casefold())],record['id']
        return sorted((r for r in records if query.strip().casefold() in r['name'].casefold()),key=key)

    def export_snapshot(self):
        with self._lock:return deepcopy(self._export)

    def snapshot(self):
        with self._lock:return deepcopy(self._state)

    def placement(self,instance_id):
        with self._lock:
            runtime.require(instance_id in self._state['placements'],'Unknown placement instance ID')
            return deepcopy(self._state['placements'][instance_id])

    def select(self,instance_id):
        with self._lock:
            runtime.require(instance_id is None or instance_id in {i['id'] for i in self._export['instances']},'Select an active instance by ID')
            self._selected=instance_id;self._generation+=1
            return self.placement(instance_id) if instance_id is not None else None

    def apply_selected(self,translation,rotation,selection_token):
        """Reject queued edits from a previous selection, even after switching A → B → A."""
        candidate=runtime.pose(translation,rotation)
        with self._lock:
            runtime.require(self._selected is not None and selection_token==(self._selected,self._generation),'Selection changed; reload the selected placement before applying')
            return self.update_many({self._selected:candidate})

    def update_many(self,placements):
        """Atomic programmatic updates; no UI, file I/O or name-based addressing."""
        with self._lock:
            runtime.require(isinstance(placements,dict),'Placement updates must be keyed by instance ID')
            active={i['id'] for i in self._export['instances']};updates={}
            for key,value in placements.items():
                runtime.require(key in active,'Cannot update an inactive/unknown instance: '+str(key))
                runtime.require(isinstance(value,dict) and 'translation_mm' in value and 'rotation_deg' in value,'Invalid placement update')
                # Preserve any existing extension metadata without changing the schema.
                updates[key]=deepcopy(self._state['placements'][key]);updates[key].update(runtime.pose(value['translation_mm'],value['rotation_deg']))
            changed={key:value for key,value in updates.items() if value!=self._state['placements'][key]}
            if changed:
                self._state['placements'].update(changed);self.state_version+=1
                if self._selected in changed:self._generation+=1
            return bool(changed)

    def refresh_export(self,export,export_path=None):
        runtime.validate_export(export)
        with self._lock:
            runtime.require(export['project']['id']==self._export['project']['id'],'Cannot merge placements from another project')
            if export_path is not None:self.export_path=str(export_path)
            if export==self._export:return False
            state=runtime.reconcile_placements(export,self._state)
            if state!=self._state:self.state_version+=1
            self._state=state;self._export=deepcopy(export);self.export_version+=1
            if self._selected not in {i['id'] for i in export['instances']}:
                self._selected=None;self._generation+=1
            return True

    def save(self):
        with self._lock:
            runtime.require(bool(self.placement_path),'Set PlacementPath before saving')
            runtime.save_placements(self.placement_path,self._state,self.export_path)
            self._saved=deepcopy(self._state)

    def reload(self):
        with self._lock:
            runtime.require(self.placement_path is not None and Path(self.placement_path).is_file(),'No saved placement file exists; save placements first')
            loaded=runtime.load_placements(self.placement_path,self._export['project']['id'])
            self._validate_state(loaded,self._export['project']['id'])
            candidate=runtime.reconcile_placements(self._export,loaded)
            if candidate!=self._state:self.state_version+=1
            self._saved=deepcopy(loaded);self._state=candidate;self._generation+=1

    def parameters(self):
        """Active instances with parameters and homogeneous local-to-world matrices."""
        with self._lock:
            result=[]
            for instance in sorted(self._export['instances'],key=lambda i:i['id']):
                placement=deepcopy(self._state['placements'][instance['id']])
                result.append({'instance_id':instance['id'],'name':instance['name'],**placement,'matrix':runtime.matrix(placement)})
            return result


class CommandEdges:
    """Momentary GH commands fire once; held toggles cannot replay on selection solves."""
    def __init__(self):self._previous={}

    def consume(self,values):
        current={key:bool(value) for key,value in values.items()}
        rising=[key for key,value in current.items() if value and not self._previous.get(key,False)]
        self._previous=current
        runtime.require(not ('Save' in rising and 'Reload' in rising),'Use Save and Reload separately')
        return rising
