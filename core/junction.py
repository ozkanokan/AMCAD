from core.component_definition import ComponentDefinition
from core.port import PortDefinition


def junction_definition(ways, definition_id=None):
    if ways not in (3, 4):
        raise ValueError("Junctions must have exactly 3 or 4 ports")
    sides = ["LEFT", "RIGHT", "BOTTOM"] + (["TOP"] if ways == 4 else [])
    return ComponentDefinition(
        definition_id or f"junction-{ways}", f"{ways}-Way Junction", "J", "Connectivity",
        [PortDefinition(side, side.title(), flow_direction="BIDIRECTIONAL", side=side) for side in sides],
        symbol={"kind": "junction", "width": 40, "height": 40},
        internal_relationships=[{"from_port_id": "LEFT", "to_port_id": side, "relationship": "JUNCTION"}
                                for side in sides[1:]],
    )
