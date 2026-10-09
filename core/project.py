"""Persistent graph operations, validation and atomic JSON persistence."""
import json
import math
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from core.component_definition import ComponentDefinition
from core.component_instance import ComponentInstance
from core.cavity_definition import CavityDefinition
from copy import deepcopy
from core.connection import Connection
from core.port import Node, new_id
from core.line_geometry import endpoint, routed_geometry, validate_geometry

SCHEMA_VERSION = 7


def write_json(path, data):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".amcad-", delete=False) as stream:
            temporary = stream.name
            json.dump(data, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


class Project:
    def __init__(self, name="Untitled"):
        self.metadata = {"id": new_id(), "name": name}
        self.definitions = {}
        self.instances = {}
        self.nodes = {}
        self.connections = {}
        self.cavities = {}

    def effective_definition(self, instance_id):
        instance=self.instances[instance_id]
        definition=deepcopy(self.definitions[instance.definition_id])
        if definition.id in ('generic-2','generic-4','generic-n'):
            definition.symbol['configurable_ports']=True
        ids={p.id for p in definition.ports}
        if not isinstance(instance.port_names,dict) or not isinstance(instance.port_sides,dict) or (set(instance.port_names)|set(instance.port_sides))-ids:
            raise ValueError('Port overrides reference unknown port IDs')
        for port in definition.ports:
            port.display_name=instance.port_names.get(port.id,port.display_name)
            port.side=instance.port_sides.get(port.id,port.side)
        return definition.validate()

    def configure_ports(self, instance_id, names, sides):
        instance=self.instances[instance_id]
        previous=(instance.port_names,instance.port_sides)
        instance.port_names=deepcopy(names);instance.port_sides=deepcopy(sides)
        try:self.effective_definition(instance_id)
        except (ValueError,TypeError,AttributeError):
            instance.port_names,instance.port_sides=previous
            raise ValueError('Port labels must be nonempty and sides must be valid')
        self.update_geometry()

    def resize_generic(self, instance_id, count):
        from core.generic import resized_generic
        instance=self.instances[instance_id];old=self.effective_definition(instance_id)
        if not old.symbol.get('configurable_ports'):raise ValueError('This component has a fixed port count')
        if count==len(old.ports):return
        if instance.cavity_ref:raise ValueError('Remove the cavity assignment before changing the port count')
        definition=resized_generic(old,count)
        removed={p.id for p in old.ports}-{p.id for p in definition.ports}
        for pid in removed:
            node=self.node_for(instance_id,pid)
            if any(node.id in (c.from_node_id,c.to_node_id) for c in self.connections.values()):
                raise ValueError('Disconnect occupied ports before removing them')
        self.add_definition(definition);instance.definition_id=definition.id
        self.nodes={key:node for key,node in self.nodes.items() if not (node.instance_id==instance_id and node.port_id in removed)}
        for port in definition.ports:
            if not any(n.instance_id==instance_id and n.port_id==port.id for n in self.nodes.values()):
                node=Node(new_id(),instance_id,port.id);self.nodes[node.id]=node
        instance.port_names={k:v for k,v in instance.port_names.items() if k not in removed}
        instance.port_sides={k:v for k,v in instance.port_sides.items() if k not in removed}
        self.update_geometry()

    def cavity_usage(self,cavity_id):
        return [i for i in self.instances.values() if i.cavity_ref==cavity_id]

    def validate_assignment(self,instance,cavity,mapping):
        cavity.validate()
        expected={p.id for p in self.definitions[instance.definition_id].ports}
        if not isinstance(mapping,dict) or set(mapping)!=expected:raise ValueError('Cavity assignment requires every schematic port')
        if len(expected)!=cavity.port_count:raise ValueError('Cavity hydraulic interface count is incompatible')
        values=list(mapping.values())
        if any(not isinstance(v,str) for v in values) or len(values)!=len(set(values)) or set(values)!={m.id for m in cavity.interfaces}:
            raise ValueError('Cavity mapping must be complete and one-to-one')

    def assign_cavity(self,instance_id,cavity,mapping):
        instance=self.instances[instance_id]
        self.validate_assignment(instance,cavity,mapping)
        old=self.cavities.get(cavity.id)
        if old is not None and old.to_dict()!=cavity.to_dict():
            raise ValueError('Project snapshot differs; explicitly refresh the shared cavity before assigning')
        previous=instance.cavity_ref
        self.cavities[cavity.id]=deepcopy(cavity)
        instance.cavity_ref=cavity.id;instance.port_mapping=deepcopy(mapping)
        if previous and previous!=cavity.id and not self.cavity_usage(previous):self.cavities.pop(previous,None)

    def remove_cavity_assignment(self,instance_id):
        instance=self.instances[instance_id];previous=instance.cavity_ref
        instance.cavity_ref=None;instance.port_mapping={}
        if previous and not self.cavity_usage(previous):self.cavities.pop(previous,None)

    def update_cavity(self,cavity):
        cavity.validate()
        # Validate every affected mapping before changing the shared snapshot.
        for instance in self.cavity_usage(cavity.id):self.validate_assignment(instance,cavity,instance.port_mapping)
        if self.cavity_usage(cavity.id):self.cavities[cavity.id]=deepcopy(cavity)

    def add_definition(self, definition):
        definition.validate()
        old = self.definitions.get(definition.id)
        if old and old != definition:
            raise ValueError("Definition ID already exists with different contents")
        self.definitions[definition.id] = definition

    def add_instance(self, definition, x=0, y=0, name=None):
        self.add_definition(definition)
        if name is None:
            index = 1
            names = {i.name for i in self.instances.values()}
            while f"{definition.prefix}{index}" in names:
                index += 1
            name = f"{definition.prefix}{index}"
        self._check_name(name)
        instance = ComponentInstance(definition.id, name.strip(), x, y)
        self.instances[instance.id] = instance
        kind = {"external": "external_port", "junction": "junction"}.get(definition.symbol.get("kind"), "component_port")
        for port in definition.ports:
            node = Node(new_id(), instance.id, port.id, kind)
            self.nodes[node.id] = node
        return instance

    def _check_name(self, name, except_id=None):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Instance name cannot be empty")
        if any(i.name == name.strip() and i.id != except_id for i in self.instances.values()):
            raise ValueError("Instance name must be unique")

    def rename(self, instance_id, name):
        self._check_name(name, instance_id)
        self.instances[instance_id].name = name.strip()

    def node_for(self, instance_id, port_id):
        return next(n for n in self.nodes.values() if n.instance_id == instance_id and n.port_id == port_id)

    def rotate(self, instance_id, degrees=90):
        if degrees % 90:
            raise ValueError("Rotation must be a multiple of 90 degrees")
        instance = self.instances[instance_id]
        instance.rotation = (instance.rotation + degrees) % 360
        self.update_geometry()

    def port_occupied(self, node_id):
        return any(node_id in (c.from_node_id, c.to_node_id) for c in self.connections.values())

    def _check_port(self, node_id):
        if self.port_occupied(node_id):
            raise ValueError("Port already has a line (occupied); use an explicit junction to branch")

    def incomplete_ports(self, instance_id):
        instance = self.instances[instance_id]
        return [p.id for p in self.definitions[instance.definition_id].ports
                if p.required and not self.port_occupied(self.node_for(instance_id, p.id).id)]

    def is_complete(self, instance_id):
        return not self.incomplete_ports(instance_id)

    def set_line_geometry(self, connection_id, controls):
        c = self.connections[connection_id]
        a, a_side = endpoint(self, c.from_node_id)
        b, b_side = endpoint(self, c.to_node_id)
        c.schematic_geometry = routed_geometry(a, a_side, b, b_side, controls)

    def update_line_geometry(self, connection_id):
        c = self.connections[connection_id]
        a, a_side = endpoint(self, c.from_node_id)
        b, b_side = endpoint(self, c.to_node_id)
        expected = routed_geometry(a, a_side, b, b_side, c.schematic_geometry.get('controls', []))
        if expected != c.schematic_geometry:
            c.schematic_geometry = expected

    def update_geometry(self):
        for connection_id in self.connections:
            self.update_line_geometry(connection_id)

    def connect(self, a, b, controls=()):
        if a not in self.nodes or b not in self.nodes:
            raise ValueError("Connection endpoint does not exist")
        if a == b:
            raise ValueError("Cannot connect a port to itself")
        if any({c.from_node_id, c.to_node_id} == {a, b} for c in self.connections.values()):
            raise ValueError("These ports are already connected")
        if self.nodes[a].instance_id == self.nodes[b].instance_id and self.nodes[a].kind == "junction":
            raise ValueError("Junction ports are already internally connected")
        self._check_port(a)
        self._check_port(b)
        source, target = self.nodes[a], self.nodes[b]
        c = Connection(a, b, from_component_instance_id=source.instance_id, from_port_id=source.port_id,
                       to_component_instance_id=target.instance_id, to_port_id=target.port_id)
        self.connections[c.id] = c
        try:
            self.set_line_geometry(c.id, controls)
        except (ValueError, TypeError):
            del self.connections[c.id]
            raise
        return c

    def remove_instance(self, instance_id):
        node_ids = {n.id for n in self.nodes.values() if n.instance_id == instance_id}
        self.connections = {k: c for k, c in self.connections.items()
                            if c.from_node_id not in node_ids and c.to_node_id not in node_ids}
        self.nodes = {k: n for k, n in self.nodes.items() if k not in node_ids}
        self.remove_cavity_assignment(instance_id)
        del self.instances[instance_id]

    def copy_subgraph(self, instance_ids):
        self.update_geometry()
        ids = set(instance_ids)
        nodes = {n.id for n in self.nodes.values() if n.instance_id in ids}
        return {"cavity_definitions":[c.to_dict() for k,c in self.cavities.items() if any(self.instances[i].cavity_ref==k for i in ids)],
                "definitions": [self.definitions[k].to_dict() for k in
                                  sorted({self.instances[i].definition_id for i in ids})],
                "instances": [asdict(self.instances[i]) for i in sorted(ids)],
                "nodes": [asdict(self.nodes[n]) for n in sorted(nodes)],
                "connections": [asdict(c) for c in self.connections.values()
                                if c.from_node_id in nodes and c.to_node_id in nodes]}

    def paste_subgraph(self,data,offset=30):
        before=deepcopy((self.definitions,self.instances,self.nodes,self.connections,self.cavities))
        try:return self._paste_subgraph(data,offset)
        except (ValueError,KeyError,TypeError):
            self.definitions,self.instances,self.nodes,self.connections,self.cavities=before
            raise

    def _paste_subgraph(self, data, offset=30):
        mapping = {}
        added = []
        cavities={c.id:c for c in (CavityDefinition.from_dict(v) for v in data.get("cavity_definitions",[]))}
        for d in data["definitions"]:
            incoming=ComponentDefinition.from_dict(d)
            existing=self.definitions.get(incoming.id)
            if existing is not None and existing.physical != incoming.physical:
                # A cavity edit applies to the reusable definition. An older
                # schematic clipboard must not restore obsolete physical data.
                old,new=existing.to_dict(),incoming.to_dict()
                old.pop('physical'); new.pop('physical')
                if old != new: raise ValueError('Copied schematic definition conflicts with the project')
            else:
                self.add_definition(incoming)
        for old in data["instances"]:
            instance = self.add_instance(self.definitions[old["definition_id"]], old["x"] + offset, old["y"] + offset)
            instance.rotation = old["rotation"]
            instance.port_names = deepcopy(old.get("port_names",{}))
            instance.port_sides = deepcopy(old.get("port_sides",{}))
            if old.get("cavity_ref"):
                cavity_id=old["cavity_ref"]
                cavity=self.cavities.get(cavity_id) or cavities.get(cavity_id)
                if cavity is None:raise ValueError("Clipboard is missing its cavity snapshot")
                self.assign_cavity(instance.id,cavity,old.get("port_mapping",{}))
            mapping[old["id"]] = instance.id
            added.append(instance.id)
        node_map = {n["id"]: self.node_for(mapping[n["instance_id"]], n["port_id"]).id for n in data["nodes"]}
        for c in data["connections"]:
            controls = [[x + offset, y + offset] for x, y in c['schematic_geometry']['controls']]
            self.connect(node_map[c["from_node_id"]], node_map[c["to_node_id"]], controls)
        return added

    def validate(self):
        if not all(isinstance(self.metadata.get(k), str) and self.metadata[k].strip() for k in ("id", "name")):
            raise ValueError("Project metadata needs an ID and name")
        for key,cavity in self.cavities.items():
            if key!=cavity.id:raise ValueError('Cavity snapshot index disagrees with its ID')
            cavity.validate()
        for definition in self.definitions.values():
            definition.validate()
        global_ids = list(self.instances) + list(self.nodes) + list(self.connections)
        if len(global_ids) != len(set(global_ids)) or any(not isinstance(i, str) or not i for i in global_ids):
            raise ValueError("Object IDs must be nonempty and unique")
        for i in self.instances.values():
            self._check_name(i.name, i.id)
            if i.definition_id not in self.definitions:
                raise ValueError("Missing component definition")
            if i.cavity_ref is not None:
                if not isinstance(i.cavity_ref,str) or i.cavity_ref not in self.cavities:raise ValueError('Missing cavity snapshot for instance assignment')
                self.validate_assignment(i,self.cavities[i.cavity_ref],i.port_mapping)
            elif i.port_mapping:raise ValueError('Port mapping without a cavity assignment')
            if i.rotation not in {0, 90, 180, 270}:
                raise ValueError("Rotation must be 0, 90, 180 or 270")
            if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (i.x, i.y)):
                raise ValueError("Invalid schematic position")
            expected = {p.id for p in self.effective_definition(i.id).ports}
            actual = [n.port_id for n in self.nodes.values() if n.instance_id == i.id]
            if len(actual) != len(expected) or set(actual) != expected:
                raise ValueError("Instance ports and nodes do not match")
        for n in self.nodes.values():
            if n.instance_id not in self.instances:
                raise ValueError("Node references a missing instance")
            definition = self.definitions[self.instances[n.instance_id].definition_id]
            kind = {"external": "external_port", "junction": "junction"}.get(definition.symbol.get("kind"), "component_port")
            if n.kind != kind:
                raise ValueError("Node kind disagrees with component definition")
        pairs = set()
        occupied_ports = set()
        for c in self.connections.values():
            if c.from_node_id not in self.nodes or c.to_node_id not in self.nodes or c.from_node_id == c.to_node_id:
                raise ValueError("Invalid connection endpoints")
            source, target = self.nodes[c.from_node_id], self.nodes[c.to_node_id]
            if (c.from_component_instance_id, c.from_port_id, c.to_component_instance_id, c.to_port_id) != (
                    source.instance_id, source.port_id, target.instance_id, target.port_id):
                raise ValueError("Connection instance/port references disagree with node IDs")
            if source.kind == "junction" and source.instance_id == target.instance_id:
                raise ValueError("Junction ports are already internally connected")
            for node in (source, target):
                if node.id in occupied_ports:
                    raise ValueError("Port is occupied by multiple lines; use an explicit junction")
                occupied_ports.add(node.id)
            validate_geometry(c.schematic_geometry)
            a, a_side = endpoint(self, c.from_node_id)
            b, b_side = endpoint(self, c.to_node_id)
            if c.schematic_geometry != routed_geometry(a, a_side, b, b_side, c.schematic_geometry['controls']):
                raise ValueError('Saved line geometry disagrees with its port endpoints or controls')
            pair = frozenset((c.from_node_id, c.to_node_id))
            if pair in pairs:
                raise ValueError("Duplicate connection")
            pairs.add(pair)
        return self

    def to_dict(self):
        self.update_geometry()
        self.validate()
        return {"schema": "amcad.project", "schema_version": SCHEMA_VERSION,
                "project": dict(self.metadata),
                "component_definitions": [d.to_dict() for d in self.definitions.values()],
                "cavity_definitions": [c.to_dict() for c in self.cavities.values()],
                "component_instances": [asdict(i) for i in self.instances.values()],
                "nodes": [asdict(n) for n in self.nodes.values()],
                "connections": [asdict(c) for c in self.connections.values()],
                "junctions": [n.id for n in self.nodes.values() if n.kind == "junction"]}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Project JSON must be an object")
        if data.get("schema") != "amcad.project" or data.get("schema_version") not in (1, 2, 3, 4, 5, 6, SCHEMA_VERSION):
            raise ValueError("Unsupported project schema/version")
        if data["schema_version"] == 1:
            from core.migration import migrate_v1
            data = migrate_v1(data)
        legacy = data['schema_version'] < 3
        if legacy:
            from core.migration import migrate_v2_branches
            data = migrate_v2_branches(data)
        p = cls()
        p.metadata = dict(data["project"])
        for key, target, constructor in (
            ("cavity_definitions",p.cavities,CavityDefinition.from_dict),
            ("component_definitions", p.definitions, ComponentDefinition.from_dict),
            ("component_instances", p.instances, lambda v: ComponentInstance(**v)),
            ("nodes", p.nodes, lambda v: Node(**v)),
            ("connections", p.connections, lambda v: Connection(**v))):
            for record in data.get(key,[]) if key=="cavity_definitions" else data[key]:
                item = constructor(record)
                if item.id in target:
                    raise ValueError(f"Duplicate ID in {key}")
                target[item.id] = item
        if set(data["junctions"]) != {n.id for n in p.nodes.values() if n.kind == "junction"}:
            raise ValueError("Junction index disagrees with nodes")
        if legacy or data["schema_version"] < 7:
            if not legacy:
                for connection in p.connections.values():validate_geometry(connection.schematic_geometry)
            p.update_geometry()
        return p.validate()

    def save(self, path):
        write_json(path, self.to_dict())

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
