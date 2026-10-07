from dataclasses import dataclass, field
from core.port import new_id


@dataclass
class Connection:
    from_node_id: str
    to_node_id: str
    id: str = field(default_factory=new_id)
    from_component_instance_id: str | None = None
    from_port_id: str | None = None
    to_component_instance_id: str | None = None
    to_port_id: str | None = None
    schematic_geometry: dict = field(default_factory=dict)
