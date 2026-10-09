"""Routing edges and component-internal relationships are separate by contract."""
from dataclasses import asdict
from core.project import write_json


def export_graph(project):
    project.validate()
    nodes = []
    for n in project.nodes.values():
        i = project.instances[n.instance_id]
        d = project.definitions[i.definition_id]
        port = next(p for p in d.ports if p.id == n.port_id)
        label = i.name if n.kind == "external_port" else f"{i.name}.{n.port_id}"
        nodes.append({**asdict(n), "label": label, "port_type": port.port_type,
                      "flow_direction": port.flow_direction, "required": port.required})
    internal = []
    for i in project.instances.values():
        for r in project.definitions[i.definition_id].internal_relationships:
            internal.append({"component_instance_id": i.id,
                             "from_node_id": project.node_for(i.id, r["from_port_id"]).id,
                             "to_node_id": project.node_for(i.id, r["to_port_id"]).id,
                             "relationship": r.get("relationship", "UNSPECIFIED")})
    return {"schema": "amcad.hydraulic_graph", "schema_version": 6,
            "component_definitions": [d.to_dict() for d in project.definitions.values()],
            "cavity_definitions": [c.to_dict() for c in project.cavities.values()],
            "project": dict(project.metadata),
            "component_instances": [{"id": i.id, "name": i.name, "definition_id": i.definition_id,
                                      "definition_name": project.definitions[i.definition_id].name,
                                      "cavity_ref":i.cavity_ref,"port_mapping":dict(i.port_mapping)}
                                     for i in project.instances.values()],
            "nodes": nodes, "junctions": [n.id for n in project.nodes.values() if n.kind == "junction"],
            "junction_instances": [{"id": i.id, "name": i.name,
                                    "port_node_ids": [n.id for n in project.nodes.values() if n.instance_id == i.id],
                                    "capacity": len(project.definitions[i.definition_id].ports)}
                                   for i in project.instances.values()
                                   if project.definitions[i.definition_id].symbol.get("kind") == "junction"],
            "routing_connections": [{**{k:v for k,v in asdict(c).items() if k != 'schematic_geometry'}, "requires_routing": True,
                                     "direction_semantics": "connectivity_only"}
                                    for c in project.connections.values()],
            "component_internal_relationships": internal}


def save_graph(project, path):
    write_json(path, export_graph(project))
