from dataclasses import dataclass, field
from core.port import new_id


@dataclass
class Connection:
    from_node_id: str
    to_node_id: str
    id: str = field(default_factory=new_id)
