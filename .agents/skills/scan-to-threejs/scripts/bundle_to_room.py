#!/usr/bin/env python3
"""Convert one room of a House Capture bundle into room coordinates for the
three.js rebuild: floor at y=0, walls aligned to X/Z, room centered.

usage: bundle_to_room.py <bundle_dir> [--room N] [-o room.json] [--plan plan.png] [--turn K]

Output JSON:
  transform  worldToRoom (column-major 4x4) + theta/center/floorY it was built from
  polygon    floor outline [[x, z], ...] in room coords (counter-clockwise seen from above)
  walls      [{index, a, b, height, origin, u, n, length, openings: [{kind, u0, u1, v0, v1}]}]
             origin = interior face, left end, floor; u runs left→right seen from inside;
             n points into the room; u × up = n (the WallDef convention in shell.ts)
  objects    [{category, center, size, rotY, front}]  (rotY turns local +z to `front`)
  photos     [{file, position, forward, up, fovY, aspect}] in room coords, upright (portrait) framing
--plan draws the result with wall indices and u ticks every 0.5 m for annotating.

The conversion itself is `convert_room`, a pure function of the RoomPlan dict and the
photo index; `main` only parses arguments, reads and writes files and prints a summary.
"""
import argparse
import json
import math
import os

# ×4 folds the 90° symmetry of a rectilinear room into one direction.
QUARTER_FOLD = 4
# How far inside the wall face (m) the interior side is probed against the floor polygon.
INTERIOR_PROBE_M = 0.05
# An opening whose bottom is closer to the floor than this (m) starts at the floor.
FLOOR_LEVEL_SILL_M = 0.06
OPENING_KINDS = ('doors', 'windows', 'openings')


def mat(t):
    """Column-major flat list of 16 values -> 4x4 row list."""
    return [[t[c * 4 + r] for c in range(4)] for r in range(4)]


def flatten(m):
    """4x4 row list -> column-major flat list of 16 values (inverse of `mat`)."""
    return [m[r][c] for c in range(4) for r in range(4)]


def col(m, c):
    return [m[0][c], m[1][c], m[2][c]]


def mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def apply(m, p, w=1.0):
    """Transform a point (w=1) or a direction (w=0) by a 4x4 matrix."""
    v = [p[0], p[1], p[2], w]
    return [sum(m[i][k] * v[k] for k in range(4)) for i in range(3)]


def floor_height(room):
    """World y of the floor: the floor surface if present, else the lowest wall bottom."""
    if room.get('floors'):
        return mat(room['floors'][0]['transform'])[1][3]
    return min(mat(w['transform'])[1][3] - w['dimensions'][1] / 2 for w in room['walls'])


def heading(walls, turn=0):
    """Angle (rad, atan2(z, x)) the walls run at, length-weighted mod 90°, minus `turn` quarters."""
    sx = sy = 0.0
    for w in walls:
        x = col(mat(w['transform']), 0)
        ang = math.atan2(x[2], x[0]) * QUARTER_FOLD
        sx += math.cos(ang) * w['dimensions'][0]
        sy += math.sin(ang) * w['dimensions'][0]
    theta = math.atan2(sy, sx) / QUARTER_FOLD  # walls run at theta (+k·90°) in world x/z
    return theta - turn * math.pi / 2


def world_to_room(walls, theta, floor_y):
    """Rotate by -theta about Y, then center the wall ends and drop the floor to y=0.

    Returns (worldToRoom 4x4, [cx, cz]) where the center is in rotated world x/z.
    """
    c, s = math.cos(-theta), math.sin(-theta)
    # rotation that maps world direction at angle theta (atan2(z, x)) onto +x
    rotation = [[c, 0, -s, 0], [0, 1, 0, 0], [s, 0, c, 0], [0, 0, 0, 1]]
    ends = []
    for w in walls:
        m = mat(w['transform'])
        ctr, x = col(m, 3), col(m, 0)
        hw = w['dimensions'][0] / 2
        for sgn in (-1, 1):
            ends.append(apply(rotation, [ctr[0] + x[0] * sgn * hw, 0, ctr[2] + x[2] * sgn * hw]))
    cx = (min(e[0] for e in ends) + max(e[0] for e in ends)) / 2
    cz = (min(e[2] for e in ends) + max(e[2] for e in ends)) / 2
    translation = [[1, 0, 0, -cx], [0, 1, 0, -floor_y], [0, 0, 1, -cz], [0, 0, 0, 1]]
    return mul(translation, rotation), [cx, cz]


def floor_polygon(room, w2r):
    """Floor outline [[x, z], ...] in room coords, counter-clockwise seen from above, or None."""
    floors = room.get('floors')
    if not (floors and floors[0].get('polygonCorners')):
        return None
    fm = mat(floors[0]['transform'])
    poly = [apply(w2r, apply(fm, [p[0], p[1], p[2]])) for p in floors[0]['polygonCorners']]
    poly = [[round(p[0], 4), round(p[2], 4)] for p in poly]
    if signed_area(poly) < 0:
        poly.reverse()
    return poly


def signed_area(poly):
    """Twice the signed area in x/(-z): positive when counter-clockwise seen from above (+y)."""
    n = len(poly)
    return sum(poly[i][0] * -poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * -poly[i][1] for i in range(n))


def inside(poly, x, z):
    """Even-odd point-in-polygon test; without a polygon every point counts as inside."""
    if not poly:
        return True
    hit = False
    for i in range(len(poly)):
        (x1, z1), (x2, z2) = poly[i], poly[(i + 1) % len(poly)]
        if (z1 > z) != (z2 > z) and x < x1 + (z - z1) * (x2 - x1) / (z2 - z1):
            hit = not hit
    return hit


def openings_by_wall(room):
    """parentIdentifier -> [(kind, element)] for doors, windows and openings, in file order."""
    kids = {}
    for kind in OPENING_KINDS:
        for e in room.get(kind, []):
            kids.setdefault(e.get('parentIdentifier'), []).append((kind[:-1], e))
    return kids


def convert_opening(kind, element, w2r, origin, u):
    """One door/window/opening as u/v extents on its wall (u from `origin`, v from the floor)."""
    ec = apply(w2r, col(mat(element['transform']), 3))
    du = (ec[0] - origin[0]) * u[0] + (ec[2] - origin[2]) * u[2]
    ew, eh = element['dimensions'][0], element['dimensions'][1]
    v0 = ec[1] - eh / 2
    return {
        'kind': kind,
        'u0': round(du - ew / 2, 3), 'u1': round(du + ew / 2, 3),
        'v0': 0.0 if v0 < FLOOR_LEVEL_SILL_M else round(v0, 3), 'v1': round(ec[1] + eh / 2, 3),
        'isOpen': bool(element['category'].get('door', {}).get('isOpen', False)) if kind == 'door' else None,
    }


def convert_wall(index, wall, w2r, poly, kids):
    """One wall in room coords, its normal turned towards the inside of `poly`."""
    m = mat(wall['transform'])
    ctr = apply(w2r, col(m, 3))
    u = apply(w2r, col(m, 0), 0.0)
    length, height = wall['dimensions'][0], wall['dimensions'][1]
    n = [-u[2], 0, u[0]]  # u × up
    if not inside(poly, ctr[0] + n[0] * INTERIOR_PROBE_M, ctr[2] + n[2] * INTERIOR_PROBE_M):
        u = [-u[0], 0, -u[2]]
        n = [-n[0], 0, -n[2]]
    origin = [ctr[0] - u[0] * length / 2, 0, ctr[2] - u[2] * length / 2]
    b = [origin[0] + u[0] * length, origin[2] + u[2] * length]
    openings = [convert_opening(kind, e, w2r, origin, u) for kind, e in kids.get(wall['identifier'], [])]
    return {
        'index': index,
        'a': [round(origin[0], 4), round(origin[2], 4)],
        'b': [round(b[0], 4), round(b[1], 4)],
        'height': round(height, 3),
        'origin': [round(v, 4) for v in origin],
        'u': [round(v, 5) for v in u],
        'n': [round(v, 5) for v in n],
        'length': round(length, 4),
        'confidence': next(iter(wall['confidence'])),
        'openings': sorted(openings, key=lambda o: o['u0']),
    }


def convert_object(obj, w2r):
    """One furniture box in room coords; rotY turns local +z onto `front`."""
    m = mat(obj['transform'])
    ctr = apply(w2r, col(m, 3))
    f = apply(w2r, col(m, 2), 0.0)
    return {
        'category': next(iter(obj['category'])),
        'center': [round(v, 3) for v in ctr],
        'size': [round(v, 3) for v in obj['dimensions']],
        'rotY': round(math.atan2(f[0], f[2]), 4),
        'front': [round(f[0], 3), round(f[2], 3)],
    }


def room_photos(photos, room_index):
    """Photos taken in room `room_index`, or all of them when it is None, in index order."""
    return [p for p in photos if room_index is None or p['room'] == room_index]


def convert_photo(photo, w2r):
    """One camera pose in room coords, upright framing: image up = sensor -x, right = sensor +y."""
    pm = mat(photo['transform'])
    pos = apply(w2r, col(pm, 3))
    fwd = apply(w2r, [-v for v in col(pm, 2)], 0.0)
    up = apply(w2r, [-v for v in col(pm, 0)], 0.0)
    fx = photo['intrinsics'][0]
    # upright image is height=sensor width; vertical fov spans the sensor's x axis
    fov_y = math.degrees(2 * math.atan(photo['width'] / 2 / fx))
    return {
        'file': photo['file'], 'position': [round(v, 4) for v in pos], 'forward': [round(v, 5) for v in fwd],
        'up': [round(v, 5) for v in up], 'fovY': round(fov_y, 3), 'aspect': round(photo['height'] / photo['width'], 5),
        'blurPixels': photo.get('blurPixels'),
    }


def convert_room(room, photos, source, turn=0):
    """RoomPlan room dict + its photos -> the room.json document.

    `photos` is already restricted to this room (see `room_photos`); `turn` adds quarter
    turns (counter-clockwise seen from above) to match another scan.
    """
    walls = room['walls']
    floor_y = floor_height(room)
    theta = heading(walls, turn)
    w2r, center = world_to_room(walls, theta, floor_y)
    poly = floor_polygon(room, w2r)
    kids = openings_by_wall(room)
    return {
        'source': source,
        'transform': {'theta': theta, 'center': center, 'floorY': floor_y, 'worldToRoom': flatten(w2r)},
        'polygon': poly,
        'walls': [convert_wall(i, w, w2r, poly, kids) for i, w in enumerate(walls)],
        'objects': [convert_object(o, w2r) for o in room.get('objects', [])],
        'photos': [convert_photo(p, w2r) for p in photos],
    }


def source_name(bundle, room_index):
    """Label of the converted room: the bundle folder name, plus the room index if any."""
    return os.path.basename(os.path.normpath(bundle)) + ('' if room_index is None else f' room {room_index}')


def summary(result, out):
    """Printed lines: overall size and counts, then one line per wall and per object."""
    walls, objects = result['walls'], result['objects']
    xs = [p for w in walls for p in (w['a'][0], w['b'][0])]
    zs = [p for w in walls for p in (w['a'][1], w['b'][1])]
    lines = [f'room {max(xs) - min(xs):.2f} × {max(zs) - min(zs):.2f} m, heights {sorted({w["height"] for w in walls})}, '
             f'{len(walls)} walls, {len(objects)} objects, {len(result["photos"])} photos → {out}']
    for w in walls:
        ops = ', '.join(f"{o['kind']} u{o['u0']:.2f}-{o['u1']:.2f} v{o['v0']:.2f}-{o['v1']:.2f}" for o in w['openings'])
        lines.append(f"  wall {w['index']:2d}: ({w['a'][0]:6.2f},{w['a'][1]:6.2f}) → ({w['b'][0]:6.2f},{w['b'][1]:6.2f})  "
                     f"len {w['length']:.2f} h {w['height']:.2f}  n ({w['n'][0]:.0f},{w['n'][2]:.0f})  {ops}")
    for o in objects:
        lines.append(f"  {o['category']:12s} center ({o['center'][0]:.2f},{o['center'][2]:.2f}) size {o['size']} "
                     f"rotY {math.degrees(o['rotY']):.0f}°")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('bundle')
    ap.add_argument('--room', type=int, default=None, help='room index (default: structure.json, all rooms)')
    ap.add_argument('-o', default=None)
    ap.add_argument('--plan', default=None)
    ap.add_argument('--turn', type=int, default=0, help='extra quarter turns (90° each, counter-clockwise seen from above) to match another scan')
    a = ap.parse_args()

    src = os.path.join(a.bundle, 'structure.json' if a.room is None else f'rooms/room-{a.room}.json')
    with open(src) as f:
        room = json.load(f)
    pj = os.path.join(a.bundle, 'photos/photos.json')
    photos = []
    if os.path.exists(pj):
        with open(pj) as f:
            photos = json.load(f)

    result = convert_room(room, room_photos(photos, a.room), source_name(a.bundle, a.room), a.turn)
    out = a.o or os.path.join(a.bundle, 'room.json')
    with open(out, 'w') as f:
        json.dump(result, f, indent=1)
    for line in summary(result, out):
        print(line)

    if a.plan:
        plan(result, a.plan)


def plan(r, path, ppm=140):
    from PIL import Image, ImageDraw
    pts = [p for w in r['walls'] for p in (w['a'], w['b'])]
    minx, maxx = min(p[0] for p in pts) - 0.5, max(p[0] for p in pts) + 0.5
    minz, maxz = min(p[1] for p in pts) - 0.5, max(p[1] for p in pts) + 0.5
    img = Image.new('RGB', (int((maxx - minx) * ppm), int((maxz - minz) * ppm)), (18, 18, 22))
    d = ImageDraw.Draw(img)
    P = lambda x, z: ((x - minx) * ppm, (z - minz) * ppm)
    for g in range(math.floor(minx * 2), math.ceil(maxx * 2) + 1):
        d.line([P(g / 2, minz), P(g / 2, maxz)], fill=(60, 60, 75) if g % 2 == 0 else (35, 35, 45))
        if g % 2 == 0:
            d.text(P(g / 2 + 0.02, minz + 0.05), f'x{g / 2:.0f}', fill=(0, 200, 255))
    for g in range(math.floor(minz * 2), math.ceil(maxz * 2) + 1):
        d.line([P(minx, g / 2), P(maxx, g / 2)], fill=(60, 60, 75) if g % 2 == 0 else (35, 35, 45))
        if g % 2 == 0:
            d.text(P(minx + 0.03, g / 2 + 0.02), f'z{g / 2:.0f}', fill=(255, 200, 0))
    for o in r['objects']:
        cx, cz = o['center'][0], o['center'][2]
        hw, hd, a = o['size'][0] / 2, o['size'][2] / 2, o['rotY']
        # local x axis = (cos a, -sin a), local z (front) = (sin a, cos a)
        corners = [(cx + math.cos(a) * sx * hw + math.sin(a) * sz * hd, cz - math.sin(a) * sx * hw + math.cos(a) * sz * hd)
                   for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        d.polygon([P(*p) for p in corners], outline=(230, 170, 60), fill=(70, 55, 30))
        d.text(P(cx, cz), o['category'], fill=(255, 210, 120))
    for w in r['walls']:
        d.line([P(*w['a']), P(*w['b'])], fill=(235, 235, 235) if w['height'] > 2.15 else (150, 150, 255), width=4)
        mx, mz = (w['a'][0] + w['b'][0]) / 2, (w['a'][1] + w['b'][1]) / 2
        d.text(P(mx + w['n'][0] * 0.15, mz + w['n'][2] * 0.15), str(w['index']), fill=(255, 255, 255))
        for k in range(int(w['length'] / 0.5) + 1):  # u ticks
            t = k * 0.5
            px, pz = w['a'][0] + w['u'][0] * t, w['a'][1] + w['u'][2] * t
            q0, q1 = P(px, pz), P(px + w['n'][0] * 0.07, pz + w['n'][2] * 0.07)
            d.line([q0, q1], fill=(255, 120, 120))
        for o in w['openings']:
            p0 = (w['a'][0] + w['u'][0] * o['u0'], w['a'][1] + w['u'][2] * o['u0'])
            p1 = (w['a'][0] + w['u'][0] * o['u1'], w['a'][1] + w['u'][2] * o['u1'])
            d.line([P(*p0), P(*p1)], fill=(80, 200, 255) if o['kind'] == 'door' else (120, 255, 160), width=8)
    for i, ph in enumerate(r['photos']):
        x, z = ph['position'][0], ph['position'][2]
        f = ph['forward']
        n = math.hypot(f[0], f[2]) or 1
        d.line([P(x, z), P(x + f[0] / n * 0.3, z + f[2] / n * 0.3)], fill=(255, 90, 160), width=2)
        d.text(P(x, z), str(i), fill=(255, 150, 200))
    img.save(path)
    print(path)


if __name__ == '__main__':
    main()
