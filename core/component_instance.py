from dataclasses import dataclass, field
from core.port import new_id


@dataclass
class ComponentInstance:
    definition_id: str
    name: str
    x: float = 0
    y: float = 0
    rotation: int = 0
    id: str = field(default_factory=new_id)
