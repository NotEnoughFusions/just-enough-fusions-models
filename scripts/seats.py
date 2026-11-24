"""Rider seats for community models.

Cobblemon seats riders on locators named seat_1, seat_2, ... in the model (the body Pokémon's riding data says which
ones it uses). A model without them leaves the rider behind while the Pokémon walks or flies off, so a model that has
no seat_1 gets seats added on top of its main body bone (the bone with the most volume, avoiding the head unless the
model is nearly all head), one behind another. Seats added to a bone move with that bone's animations.
"""
SEAT_COUNT = 4      # Most rideable Pokémon use 1 or 2 seats; unused ones do nothing.
SPACING = 6         # Pixels between seats, front to back.


def _geometries(geo):
    found = geo.get("minecraft:geometry") if isinstance(geo, dict) else None
    return found if isinstance(found, list) else []


def has_seats(geo):
    for geometry in _geometries(geo):
        for bone in geometry.get("bones") or []:
            if "seat_1" in (bone.get("locators") or {}):
                return True
    return False


def _volume(cube):
    size = cube.get("size") or [0, 0, 0]
    return abs(size[0] * size[1] * size[2])


def add_seats(geo):
    """Adds seat_1..seat_4 if the model has no seat_1. Returns the name of the bone they went on, or None."""
    if has_seats(geo):
        return None
    for geometry in _geometries(geo):
        bones = [b for b in geometry.get("bones") or [] if b.get("cubes")]
        if not bones:
            continue
        volume = {id(b): sum(_volume(c) for c in b["cubes"]) for b in bones}
        main = max(bones, key=lambda b: volume[id(b)])
        if main.get("name") == "head":
            # The head turns to look at things; sit on the biggest other bone unless the model is nearly all head.
            others = [b for b in bones if b is not main]
            if others:
                runner_up = max(others, key=lambda b: volume[id(b)])
                if volume[id(runner_up)] * 2 >= volume[id(main)]:
                    main = runner_up
        big = max(main["cubes"], key=_volume)
        (x0, _, z0), (w, _, d) = big["origin"], big["size"]
        cx, cz = x0 + w / 2, z0 + d / 2
        # Sit on the highest cube of that bone that's under the seat.
        tops = [c["origin"][1] + c["size"][1] for c in main["cubes"]
                if min(c["origin"][0], c["origin"][0] + c["size"][0]) <= cx <= max(c["origin"][0], c["origin"][0] + c["size"][0])
                and min(c["origin"][2], c["origin"][2] + c["size"][2]) <= cz <= max(c["origin"][2], c["origin"][2] + c["size"][2])]
        top = max(tops) if tops else big["origin"][1] + big["size"][1]
        locators = main.setdefault("locators", {})
        for n in range(1, SEAT_COUNT + 1):
            locators.setdefault(f"seat_{n}", [round(cx, 3), round(top, 3), round(cz + SPACING * (n - 1), 3)])
        return main.get("name")
    return None
