from dataclasses import dataclass, field, asdict
from core.port import PortDefinition


@dataclass
class ComponentDefinition:
    id: str
    name: str
    prefix: str
    category: str
    ports: list[PortDefinition]
    symbol: dict = field(default_factory=lambda: {"kind": "box", "width": 110, "height": 76})
    internal_relationships: list[dict] = field(default_factory=list)
    component_cad_path: str | None = None
    cavity_cad_path: str | None = None
    keepout_cad_path: str | None = None

    def validate(self):
        if not all(isinstance(v, str) and v.strip() for v in (self.id, self.name, self.prefix, self.category)):
            raise ValueError("Definition ID, name, prefix and category are required")
        ids = [p.id for p in self.ports]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("Each component needs uniquely identified ports")
        for p in self.ports:
            if not p.id.strip() or not p.display_name.strip() or not p.port_type.strip():
                raise ValueError("Port ID, display name and type are required")
            if p.side not in {"LEFT", "RIGHT", "TOP", "BOTTOM"}:
                raise ValueError("Invalid port side")
            if p.flow_direction not in {"IN", "OUT", "BIDIRECTIONAL", "UNSPECIFIED"}:
                raise ValueError("Invalid flow direction")
        kind = self.symbol.get("kind", "box")
        if kind not in {"box", "external", "junction"}:
            raise ValueError("Unsupported symbol kind")
        if kind in {"external", "junction"} and len(ids) != 1:
            raise ValueError("External ports and junctions each represent exactly one node")
        for key in ("width", "height"):
            value = self.symbol.get(key, 110 if key == "width" else 76)
            if not isinstance(value, (int, float)) or not 20 <= value <= 1000:
                raise ValueError("Symbol dimensions must be between 20 and 1000")
        for r in self.internal_relationships:
            if r.get("from_port_id") not in ids or r.get("to_port_id") not in ids:
                raise ValueError("Internal relationship references an unknown port")
        return self

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        data["ports"] = [PortDefinition(**p) for p in data["ports"]]
        return cls(**data).validate()
