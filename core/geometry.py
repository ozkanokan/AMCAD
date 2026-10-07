"""Pure schematic geometry; no hydraulic routing or CAD behavior."""
SIDES = ("TOP", "RIGHT", "BOTTOM", "LEFT")
SIDE_VECTORS = {"TOP": (0, -1), "RIGHT": (1, 0), "BOTTOM": (0, 1), "LEFT": (-1, 0)}
LEAD_LENGTH = 20


def rotated_side(side, rotation):
    if rotation % 90:
        raise ValueError("Rotation must be a multiple of 90 degrees")
    return SIDES[(SIDES.index(side) + rotation // 90) % 4]


def wire_points(a, a_side, b, b_side, lead=LEAD_LENGTH):
    """Orthogonal endpoint leads joined outside their outward half-planes.

    Choosing the bridge beyond both leads prevents a lead from immediately
    doubling back into its component. This is geometric drawing only, without
    obstacle avoidance. Arrival is the reverse of the destination's outward lead.
    """
    av, bv = SIDE_VECTORS[a_side], SIDE_VECTORS[b_side]
    al = (a[0] + lead * av[0], a[1] + lead * av[1])
    bl = (b[0] + lead * bv[0], b[1] + lead * bv[1])

    def bridge(axis):
        low, high = sorted((al[axis], bl[axis]))
        positive = [p[axis] for p, v in ((al, av), (bl, bv)) if v[axis] > 0]
        negative = [p[axis] for p, v in ((al, av), (bl, bv)) if v[axis] < 0]
        lower = max(positive) if positive else low - lead
        upper = min(negative) if negative else high + lead
        if lower <= upper:
            return (lower + upper) / 2
        return None

    if av[0] and bv[0]:
        mid = bridge(0)
        if mid is not None:
            middle = [(mid, al[1]), (mid, bl[1])]
        else:
            y = min(al[1], bl[1]) - lead
            middle = [(al[0], y), (bl[0], y)]
    elif av[1] and bv[1]:
        mid = bridge(1)
        if mid is not None:
            middle = [(al[0], mid), (bl[0], mid)]
        else:
            x = min(al[0], bl[0]) - lead
            middle = [(x, al[1]), (x, bl[1])]
    else:
        corner = (al[0], bl[1]) if av[0] else (bl[0], al[1])
        candidate = []
        for point in (al, corner, bl):
            if not candidate or point != candidate[-1]:
                candidate.append(point)
        def outward(start, next_point, vector):
            return sum((next_point[i] - start[i]) * vector[i] for i in (0, 1)) >= 0
        if len(candidate) > 1 and outward(al, candidate[1], av) and outward(bl, candidate[-2], bv):
            middle = [corner]
        else:
            x, y = bridge(0), bridge(1)
            middle = [(x, al[1]), (x, y), (bl[0], y)]
    result = []
    for point in [a, al, *middle, bl, b]:
        if not result or point != result[-1]:
            result.append(point)
    return result
