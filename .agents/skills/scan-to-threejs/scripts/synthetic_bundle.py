"""A small, fully synthetic House Capture bundle for the bundle_to_room tests.

The room is a 4 m x 3 m rectangle turned by HEADING about Y, with a door, a window, an
opening, two pieces of furniture and photos from two rooms. Every value is chosen so that
each branch of the conversion is reached: a polygon given clockwise, walls whose RoomPlan
x axis points either way, an opening that starts at floor level, a door left ajar.
"""
import json
import math
from pathlib import Path

HEADING = 0.3
CENTER_X, CENTER_Z = 1.5, -2.0
FLOOR_Y = 0.05
HALF_LENGTH, HALF_DEPTH = 2.0, 1.5
TALL, SHORT = 2.5, 2.1
# A small skew on one wall so the length-weighted heading is not trivially HEADING.
SKEW = 0.01


def pose(x, y, z, yaw):
    """Column-major rigid transform: local +x at `yaw` (atan2(z, x)) in world x/z, +y up."""
    c, s = math.cos(yaw), math.sin(yaw)
    return [c, 0, s, 0, 0, 1, 0, 0, -s, 0, c, 0, x, y, z, 1]


def local(lx, y, lz, yaw=0.0):
    """Pose given in the room's own (unturned, uncentered) frame."""
    c, s = math.cos(HEADING), math.sin(HEADING)
    return pose(CENTER_X + lx * c - lz * s, y, CENTER_Z + lx * s + lz * c, HEADING + yaw)


def wall(identifier, lx, lz, yaw, length, height, confidence='high'):
    return {'identifier': identifier, 'transform': local(lx, FLOOR_Y + height / 2, lz, yaw),
            'dimensions': [length, height, 0], 'confidence': {confidence: {}}}


def on_wall(parent, lx, lz, yaw, y, width, height, category):
    return {'parentIdentifier': parent, 'transform': local(lx, FLOOR_Y + y, lz, yaw),
            'dimensions': [width, height, 0], 'category': category}


def walls():
    return [
        wall('w0', 0, -HALF_DEPTH, 0, 2 * HALF_LENGTH, TALL),
        wall('w1', HALF_LENGTH, 0, math.pi / 2 + SKEW, 2 * HALF_DEPTH, TALL, 'medium'),
        wall('w2', 0, HALF_DEPTH, 0, 2 * HALF_LENGTH, TALL),
        wall('w3', -HALF_LENGTH, 0, -math.pi / 2, 2 * HALF_DEPTH, SHORT, 'low'),
    ]


def room_plan(floor=True, corners=True):
    room = {
        'walls': walls(),
        'doors': [
            on_wall('w0', 0.5, -HALF_DEPTH, 0, 1.02, 0.9, 2.0, {'door': {'isOpen': True}}),
            on_wall('w2', 1.2, HALF_DEPTH, 0, 1.0, 0.8, 2.0, {'door': {'isOpen': False}}),
            on_wall('w2', -1.3, HALF_DEPTH, 0, 1.0, 0.7, 2.0, {'door': {}}),
        ],
        'windows': [on_wall('w1', HALF_LENGTH, 0.4, math.pi / 2, 1.5, 1.0, 1.0, {'window': {}})],
        'openings': [
            on_wall('w2', -0.2, HALF_DEPTH, 0, 1.2, 1.2, 2.2, {'opening': {}}),
            on_wall('ghost', 0, 0, 0, 1.0, 1.0, 1.0, {'opening': {}}),
        ],
        'objects': [
            {'category': {'table': {}}, 'transform': local(0.5, FLOOR_Y + 0.4, 0.3, 0.2),
             'dimensions': [1.2, 0.8, 0.6]},
            {'category': {'sofa': {}}, 'transform': local(-1.2, FLOOR_Y + 0.45, 0.9, math.pi),
             'dimensions': [2.0, 0.9, 0.95]},
        ],
    }
    if floor:
        room['floors'] = [{'transform': local(0, FLOOR_Y, 0)}]
        if corners:  # clockwise seen from above, so the converter has to reverse it
            room['floors'][0]['polygonCorners'] = [
                [-HALF_LENGTH, 0, -HALF_DEPTH], [-HALF_LENGTH, 0, HALF_DEPTH],
                [HALF_LENGTH, 0, HALF_DEPTH], [HALF_LENGTH, 0, -HALF_DEPTH]]
    return room


def photos():
    def photo(index, room, lx, lz, yaw, blur=None):
        entry = {'file': f'photos/{index:04d}.jpg', 'room': room,
                 'transform': local(lx, FLOOR_Y + 1.4, lz, yaw),
                 'intrinsics': [1500, 0, 0, 0, 1500, 0, 960, 720, 1],
                 'width': 1920, 'height': 1440}
        if blur is not None:
            entry['blurPixels'] = blur
        return entry
    return [photo(0, 0, 0.2, 0.1, 0.4, 0.5), photo(1, 1, -0.5, 0.6, 1.1),
            photo(2, 0, 1.0, -0.7, -2.0, 1.25), photo(3, 1, 0.0, 0.0, 3.0, 0.0)]


def write_bundle(path, *, structure=None, rooms=None, with_photos=True):
    """Write a bundle folder: optional structure.json, rooms/room-N.json and photos.json."""
    path.mkdir(parents=True)
    if structure is not None:
        (path / 'structure.json').write_text(json.dumps(structure))
    for number, room in (rooms or {}).items():
        (path / 'rooms').mkdir(exist_ok=True)
        (path / f'rooms/room-{number}.json').write_text(json.dumps(room))
    if with_photos:
        (path / 'photos').mkdir()
        (path / 'photos/photos.json').write_text(json.dumps(photos()))
    return Path(path)
