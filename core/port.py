from dataclasses import dataclass
from uuid import uuid4


def new_id():
    return str(uuid4())


@dataclass
class PortDefinition:
    id: str
    display_name: str
    port_type: str = "HYDRAULIC"
    flow_direction: str = "UNSPECIFIED"
    side: str = "LEFT"
    local_position_xyz: list | None = None
    local_direction_xyz: list | None = None


@dataclass
class Node:
    id: str
    instance_id: str
    port_id: str
    kind: str = "component_port"
