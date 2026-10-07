"""Persistent graph operations, validation and atomic JSON persistence."""
import json
import math
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from core.component_definition import ComponentDefinition
from core.component_instance import ComponentInstance
from core.connection import Connection
from core.port import Node, new_id

SCHEMA_VERSION = 2


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

    def _check_junction_port(self, node_id):
        if self.nodes[node_id].kind == "junction" and any(
                node_id in (c.from_node_id, c.to_node_id) for c in self.connections.values()):
            raise ValueError("Junction port is occupied; choose a free port or a 4-Way Junction")

    def connect(self, a, b):
        if a not in self.nodes or b not in self.nodes:
            raise ValueError("Connection endpoint does not exist")
        if a == b:
            raise ValueError("Cannot connect a port to itself")
        if any({c.from_node_id, c.to_node_id} == {a, b} for c in self.connections.values()):
            raise ValueError("These ports are already connected")
        if self.nodes[a].instance_id == self.nodes[b].instance_id and self.nodes[a].kind == "junction":
            raise ValueError("Junction ports are already internally connected")
        self._check_junction_port(a)
        self._check_junction_port(b)
        source, target = self.nodes[a], self.nodes[b]
        c = Connection(a, b, from_component_instance_id=source.instance_id, from_port_id=source.port_id,
                       to_component_instance_id=target.instance_id, to_port_id=target.port_id)
        self.connections[c.id] = c
        return c

    def remove_instance(self, instance_id):
        node_ids = {n.id for n in self.nodes.values() if n.instance_id == instance_id}
        self.connections = {k: c for k, c in self.connections.items()
                            if c.from_node_id not in node_ids and c.to_node_id not in node_ids}
        self.nodes = {k: n for k, n in self.nodes.items() if k not in node_ids}
        del self.instances[instance_id]

    def copy_subgraph(self, instance_ids):
        ids = set(instance_ids)
        nodes = {n.id for n in self.nodes.values() if n.instance_id in ids}
        return {"definitions": [self.definitions[k].to_dict() for k in
                                  sorted({self.instances[i].definition_id for i in ids})],
                "instances": [asdict(self.instances[i]) for i in sorted(ids)],
                "nodes": [asdict(self.nodes[n]) for n in sorted(nodes)],
                "connections": [asdict(c) for c in self.connections.values()
                                if c.from_node_id in nodes and c.to_node_id in nodes]}

    def paste_subgraph(self, data, offset=30):
        mapping = {}
        added = []
        for d in data["definitions"]:
            self.add_definition(ComponentDefinition.from_dict(d))
        for old in data["instances"]:
            instance = self.add_instance(self.definitions[old["definition_id"]], old["x"] + offset, old["y"] + offset)
            instance.rotation = old["rotation"]
            mapping[old["id"]] = instance.id
            added.append(instance.id)
        node_map = {n["id"]: self.node_for(mapping[n["instance_id"]], n["port_id"]).id for n in data["nodes"]}
        for c in data["connections"]:
            self.connect(node_map[c["from_node_id"]], node_map[c["to_node_id"]])
        return added

    def validate(self):
        if not all(isinstance(self.metadata.get(k), str) and self.metadata[k].strip() for k in ("id", "name")):
            raise ValueError("Project metadata needs an ID and name")
        for definition in self.definitions.values():
            definition.validate()
        global_ids = list(self.instances) + list(self.nodes) + list(self.connections)
        if len(global_ids) != len(set(global_ids)) or any(not isinstance(i, str) or not i for i in global_ids):
            raise ValueError("Object IDs must be nonempty and unique")
        for i in self.instances.values():
            self._check_name(i.name, i.id)
            if i.definition_id not in self.definitions:
                raise ValueError("Missing component definition")
            if i.rotation not in {0, 90, 180, 270}:
                raise ValueError("Rotation must be 0, 90, 180 or 270")
            if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (i.x, i.y)):
                raise ValueError("Invalid schematic position")
            expected = {p.id for p in self.definitions[i.definition_id].ports}
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
        occupied_junction_ports = set()
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
                if node.kind == "junction":
                    if node.id in occupied_junction_ports:
                        raise ValueError("Junction port is occupied by multiple connections")
                    occupied_junction_ports.add(node.id)
            pair = frozenset((c.from_node_id, c.to_node_id))
            if pair in pairs:
                raise ValueError("Duplicate connection")
            pairs.add(pair)
        return self

    def to_dict(self):
        self.validate()
        return {"schema": "amcad.project", "schema_version": SCHEMA_VERSION,
                "project": dict(self.metadata),
                "component_definitions": [d.to_dict() for d in self.definitions.values()],
                "component_instances": [asdict(i) for i in self.instances.values()],
                "nodes": [asdict(n) for n in self.nodes.values()],
                "connections": [asdict(c) for c in self.connections.values()],
                "junctions": [n.id for n in self.nodes.values() if n.kind == "junction"]}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Project JSON must be an object")
        if data.get("schema") != "amcad.project" or data.get("schema_version") not in (1, SCHEMA_VERSION):
            raise ValueError("Unsupported project schema/version")
        if data["schema_version"] == 1:
            from core.migration import migrate_v1
            data = migrate_v1(data)
        p = cls()
        p.metadata = dict(data["project"])
        for key, target, constructor in (
            ("component_definitions", p.definitions, ComponentDefinition.from_dict),
            ("component_instances", p.instances, lambda v: ComponentInstance(**v)),
            ("nodes", p.nodes, lambda v: Node(**v)),
            ("connections", p.connections, lambda v: Connection(**v))):
            for record in data[key]:
                item = constructor(record)
                if item.id in target:
                    raise ValueError(f"Duplicate ID in {key}")
                target[item.id] = item
        if set(data["junctions"]) != {n.id for n in p.nodes.values() if n.kind == "junction"}:
            raise ValueError("Junction index disagrees with nodes")
        return p.validate()

    def save(self, path):
        write_json(path, self.to_dict())

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
