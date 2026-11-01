"""Unit tests of the bundle_to_room conversion functions, on small hand-made rooms."""
import contextlib
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image

import bundle_to_room as b2r
from synthetic_bundle import pose

IDENTITY = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
# Unit square in room x/z, counter-clockwise seen from above (+y): screen up is -z.
SQUARE_CCW = [[0, 0], [1, 0], [1, -1], [0, -1]]


def wall(identifier, x, z, yaw, length, height=2.5, bottom=0.0, confidence='high'):
    return {'identifier': identifier, 'transform': pose(x, bottom + height / 2, z, yaw),
            'dimensions': [length, height, 0], 'confidence': {confidence: {}}}


def box(x, y, z, yaw=0.0, size=(1, 1, 1), category='table'):
    return {'category': {category: {}}, 'transform': pose(x, y, z, yaw), 'dimensions': list(size)}


def translation(x, y, z):
    return [[1, 0, 0, x], [0, 1, 0, y], [0, 0, 1, z], [0, 0, 0, 1]]


def assert_close(test, actual, expected, places=7):
    test.assertEqual(len(actual), len(expected))
    for a, e in zip(actual, expected):
        test.assertAlmostEqual(a, e, places=places)


class MatrixTests(unittest.TestCase):
    def test_mat_reads_sixteen_values_column_by_column(self):
        m = b2r.mat(list(range(16)))
        self.assertEqual(m[0], [0, 4, 8, 12])
        self.assertEqual(m[3], [3, 7, 11, 15])

    def test_flatten_writes_back_what_mat_read(self):
        self.assertEqual(b2r.flatten(b2r.mat(list(range(16)))), list(range(16)))

    def test_col_returns_the_xyz_part_of_a_column(self):
        self.assertEqual(b2r.col(b2r.mat(list(range(16))), 3), [12, 13, 14])

    def test_mul_applies_the_right_matrix_first(self):
        quarter = b2r.mat(pose(0, 0, 0, math.pi / 2))
        moved_then_turned = b2r.mul(quarter, translation(1, 0, 0))
        assert_close(self, b2r.apply(moved_then_turned, [0, 0, 0]), [0, 0, 1])

    def test_apply_moves_a_point_by_default(self):
        self.assertEqual(b2r.apply(translation(1, 2, 3), [1, 1, 1]), [2, 3, 4])

    def test_apply_leaves_a_direction_unmoved(self):
        self.assertEqual(b2r.apply(translation(1, 2, 3), [1, 1, 1], 0.0), [1, 1, 1])


class FloorHeightTests(unittest.TestCase):
    def test_floor_surface_gives_the_height_when_present(self):
        room = {'floors': [{'transform': pose(5, 0.3, 5, 0)}], 'walls': [wall('w', 0, 0, 0, 2, bottom=-1)]}
        self.assertEqual(b2r.floor_height(room), 0.3)

    def test_lowest_wall_bottom_gives_the_height_without_floor(self):
        room = {'walls': [wall('a', 0, 0, 0, 2, height=2, bottom=0.2),
                          wall('b', 0, 0, 0, 2, height=3, bottom=0.1)]}
        self.assertAlmostEqual(b2r.floor_height(room), 0.1)

    def test_empty_floor_list_falls_back_to_the_walls(self):
        room = {'floors': [], 'walls': [wall('a', 0, 0, 0, 2, height=2, bottom=0.4)]}
        self.assertAlmostEqual(b2r.floor_height(room), 0.4)


class HeadingTests(unittest.TestCase):
    def test_walls_along_world_x_give_zero(self):
        self.assertAlmostEqual(b2r.heading([wall('a', 0, 0, 0, 2), wall('b', 0, 0, math.pi / 2, 2)]), 0)

    def test_perpendicular_walls_share_one_heading(self):
        walls = [wall('a', 0, 0, 0.3, 2), wall('b', 0, 0, 0.3 + math.pi / 2, 3), wall('c', 0, 0, 0.3 + math.pi, 1)]
        self.assertAlmostEqual(b2r.heading(walls), 0.3)

    def test_longer_walls_weigh_more(self):
        walls = [wall('long', 0, 0, 0.1, 3, height=1), wall('short', 0, 0, -0.1, 1, height=1)]
        # Folded angles are +-0.4 weighted 3:1.
        self.assertAlmostEqual(b2r.heading(walls), math.atan(0.5 * math.tan(0.4)) / 4)

    def test_each_turn_subtracts_a_quarter(self):
        walls = [wall('a', 0, 0, 0.2, 2)]
        self.assertAlmostEqual(b2r.heading(walls, turn=3), 0.2 - 3 * math.pi / 2)


class WorldToRoomTests(unittest.TestCase):
    def setUp(self):
        # Wall ends span x in [1, 5] and z in [2, 4].
        self.walls = [wall('s', 3, 2, 0, 4), wall('e', 5, 3, math.pi / 2, 2)]

    def test_center_of_the_wall_ends_becomes_the_origin_at_floor_level(self):
        w2r, center = b2r.world_to_room(self.walls, 0.0, 0.2)
        assert_close(self, center, [3, 3])
        assert_close(self, b2r.apply(w2r, [3, 0.2, 3]), [0, 0, 0])

    def test_direction_at_theta_maps_onto_room_x(self):
        w2r, _ = b2r.world_to_room(self.walls, 0.5, 0.0)
        assert_close(self, b2r.apply(w2r, [math.cos(0.5), 0, math.sin(0.5)], 0.0), [1, 0, 0])

    def test_center_is_measured_after_rotation(self):
        walls = [wall('s', 3, 0, 0, 2)]  # ends at x 2 and 4 on z = 0
        _, center = b2r.world_to_room(walls, math.pi / 2, 0.0)
        assert_close(self, center, [0, -3])


class FloorPolygonTests(unittest.TestCase):
    def floor(self, corners, transform=None):
        return {'floors': [{'transform': transform or pose(0, 0, 0, 0), 'polygonCorners': corners}]}

    def test_no_floor_gives_no_polygon(self):
        self.assertIsNone(b2r.floor_polygon({'walls': []}, IDENTITY))

    def test_floor_without_corners_gives_no_polygon(self):
        self.assertIsNone(b2r.floor_polygon({'floors': [{'transform': pose(0, 0, 0, 0)}]}, IDENTITY))

    def test_corners_go_through_the_floor_then_the_room_transform(self):
        room = self.floor([[0, 0, 0], [1, 0, 0], [1, 0, -1]], pose(10, 0, 20, 0))
        self.assertEqual(b2r.floor_polygon(room, translation(-10, 0, -20)), [[0, 0], [1, 0], [1, -1]])

    def test_corners_are_rounded_to_a_tenth_of_a_millimetre(self):
        room = self.floor([[0.123456, 0, 0], [1, 0, 0], [1, 0, -1]])
        self.assertEqual(b2r.floor_polygon(room, IDENTITY)[0], [0.1235, 0])

    def test_counter_clockwise_corners_keep_their_order(self):
        room = self.floor([[x, 0, z] for x, z in SQUARE_CCW])
        self.assertEqual(b2r.floor_polygon(room, IDENTITY), SQUARE_CCW)

    def test_clockwise_corners_are_reversed(self):
        room = self.floor([[x, 0, z] for x, z in reversed(SQUARE_CCW)])
        self.assertEqual(b2r.floor_polygon(room, IDENTITY), SQUARE_CCW)


class PolygonTests(unittest.TestCase):
    def test_signed_area_is_twice_the_area_counter_clockwise(self):
        self.assertEqual(b2r.signed_area(SQUARE_CCW), 2)

    def test_signed_area_is_negative_clockwise(self):
        self.assertEqual(b2r.signed_area(list(reversed(SQUARE_CCW))), -2)

    def test_point_within_the_polygon_is_inside(self):
        self.assertTrue(b2r.inside(SQUARE_CCW, 0.5, -0.5))

    def test_point_beyond_any_edge_is_outside(self):
        for x, z in [(1.5, -0.5), (-0.5, -0.5), (0.5, 0.5), (0.5, -1.5)]:
            self.assertFalse(b2r.inside(SQUARE_CCW, x, z), (x, z))

    def test_notch_of_a_concave_polygon_is_outside(self):
        ell = [[0, 0], [2, 0], [2, 1], [1, 1], [1, 2], [0, 2]]
        self.assertTrue(b2r.inside(ell, 0.5, 1.5))
        self.assertFalse(b2r.inside(ell, 1.5, 1.5))

    def test_every_point_is_inside_without_polygon(self):
        self.assertTrue(b2r.inside(None, 99, 99))
        self.assertTrue(b2r.inside([], 99, 99))


class OpeningTests(unittest.TestCase):
    def element(self, x, y, width, height, category, parent='w'):
        return {'parentIdentifier': parent, 'transform': pose(x, y, 0, 0),
                'dimensions': [width, height, 0], 'category': category}

    def test_elements_are_grouped_by_parent_wall_with_singular_kinds(self):
        door, window, gap = (self.element(0, 1, 1, 2, {'door': {}}), self.element(0, 1, 1, 1, {'window': {}}),
                             self.element(0, 1, 1, 2, {'opening': {}}, parent='other'))
        room = {'openings': [gap], 'windows': [window], 'doors': [door]}
        self.assertEqual(b2r.openings_by_wall(room), {'w': [('door', door), ('window', window)],
                                                      'other': [('opening', gap)]})

    def test_element_without_parent_is_grouped_under_none(self):
        orphan = {'transform': pose(0, 0, 0, 0)}
        self.assertEqual(b2r.openings_by_wall({'doors': [orphan]}), {None: [('door', orphan)]})

    def test_extents_are_measured_along_u_from_the_wall_origin(self):
        o = b2r.convert_opening('window', self.element(3, 1.5, 1, 0.8, {'window': {}}), IDENTITY, [1, 0, 0], [1, 0, 0])
        self.assertEqual(o, {'kind': 'window', 'u0': 1.5, 'u1': 2.5, 'v0': 1.1, 'v1': 1.9, 'isOpen': None})

    def test_extents_follow_a_reversed_u(self):
        o = b2r.convert_opening('window', self.element(3, 1.5, 1, 0.8, {'window': {}}), IDENTITY, [5, 0, 0], [-1, 0, 0])
        self.assertEqual((o['u0'], o['u1']), (1.5, 2.5))

    def test_extents_are_rounded_to_the_millimetre(self):
        o = b2r.convert_opening('window', self.element(1.23456, 1.23456, 0, 0, {'window': {}}),
                                IDENTITY, [0, 0, 0], [1, 0, 0])
        self.assertEqual((o['u0'], o['u1'], o['v0'], o['v1']), (1.235, 1.235, 1.235, 1.235))

    def test_bottom_just_above_the_floor_snaps_to_zero(self):
        o = b2r.convert_opening('opening', self.element(0, 1.05, 1, 2, {}), IDENTITY, [0, 0, 0], [1, 0, 0])
        self.assertEqual(o['v0'], 0.0)
        self.assertIs(type(o['v0']), float)

    def test_bottom_at_the_sill_threshold_is_kept(self):
        o = b2r.convert_opening('opening', self.element(0, 1.06, 1, 2, {}), IDENTITY, [0, 0, 0], [1, 0, 0])
        self.assertEqual(o['v0'], 0.06)

    def test_door_reports_whether_it_is_open(self):
        for category, expected in [({'door': {'isOpen': True}}, True), ({'door': {'isOpen': 0}}, False),
                                   ({'door': {}}, False), ({}, False)]:
            o = b2r.convert_opening('door', self.element(0, 1, 1, 2, category), IDENTITY, [0, 0, 0], [1, 0, 0])
            self.assertIs(o['isOpen'], expected, category)

    def test_window_has_no_open_state(self):
        o = b2r.convert_opening('window', self.element(0, 1, 1, 1, {'door': {'isOpen': True}}),
                                IDENTITY, [0, 0, 0], [1, 0, 0])
        self.assertIsNone(o['isOpen'])


class WallTests(unittest.TestCase):
    # Room x in [0, 4], z in [-2, 0] with identity transform; south wall on z = 0.
    POLY = [[0, 0], [4, 0], [4, -2], [0, -2]]

    def test_wall_facing_the_room_keeps_its_direction(self):
        w = b2r.convert_wall(7, wall('w', 2, -2, 0, 4, height=2.4567), IDENTITY, self.POLY, {})
        self.assertEqual(w, {'index': 7, 'a': [0, -2], 'b': [4, -2], 'height': 2.457, 'origin': [0, 0, -2],
                             'u': [1, 0, 0], 'n': [0, 0, 1], 'length': 4, 'confidence': 'high', 'openings': []})

    def test_wall_facing_away_is_turned_towards_the_room(self):
        w = b2r.convert_wall(0, wall('w', 2, 0, 0, 4), IDENTITY, self.POLY, {})
        self.assertEqual((w['a'], w['b'], w['u'], w['n']), ([4, 0], [0, 0], [-1, 0, 0], [0, 0, -1]))

    def test_wall_keeps_its_direction_without_polygon(self):
        w = b2r.convert_wall(0, wall('w', 2, 0, 0, 4), IDENTITY, None, {})
        self.assertEqual(w['n'], [0, 0, 1])

    def test_wall_lies_on_the_floor_of_the_room_frame(self):
        w = b2r.convert_wall(0, wall('w', 2, -2, 0, 4, bottom=0.5), translation(0, -0.5, 0), self.POLY, {})
        self.assertEqual(w['origin'], [0, 0, -2])

    def test_positions_and_length_are_rounded_to_a_tenth_of_a_millimetre(self):
        w = b2r.convert_wall(0, wall('w', 2.123456, -2.123456, 0, 4.123456), IDENTITY, None, {})
        self.assertEqual((w['length'], w['origin'], w['a'], w['b']),
                         (4.1235, [0.0617, 0, -2.1235], [0.0617, -2.1235], [4.1852, -2.1235]))

    def test_directions_are_rounded_to_five_digits(self):
        w = b2r.convert_wall(0, wall('w', 0, 0, 0.1, 4), IDENTITY, None, {})
        self.assertEqual(w['u'], [round(math.cos(0.1), 5), 0, round(math.sin(0.1), 5)])
        self.assertEqual(w['n'], [round(-math.sin(0.1), 5), 0, round(math.cos(0.1), 5)])

    def test_confidence_is_the_first_reported_level(self):
        w = b2r.convert_wall(0, wall('w', 2, -2, 0, 4, confidence='low'), IDENTITY, None, {})
        self.assertEqual(w['confidence'], 'low')

    def test_openings_of_this_wall_only_are_sorted_along_u(self):
        def door(x):
            return ('door', {'transform': pose(x, 1, -2, 0), 'dimensions': [0.5, 2, 0], 'category': {'door': {}}})
        kids = {'w': [door(3), door(1)], 'other': [door(2)]}
        w = b2r.convert_wall(0, wall('w', 2, -2, 0, 4), IDENTITY, self.POLY, kids)
        self.assertEqual([o['u0'] for o in w['openings']], [0.75, 2.75])


class ObjectTests(unittest.TestCase):
    def test_object_center_and_size_are_in_room_coords_to_the_millimetre(self):
        o = b2r.convert_object(box(1.23456, 0.5, 2, size=(1.23456, 0.5, 2)), translation(-1, 0, 0))
        self.assertEqual((o['category'], o['center'], o['size']), ('table', [0.235, 0.5, 2], [1.235, 0.5, 2]))

    def test_rotation_turns_local_z_onto_the_front(self):
        # pose yaw 0 has local +z along world +z; yaw -pi/2 turns it onto world +x.
        o = b2r.convert_object(box(0, 0, 0, yaw=-math.pi / 2), IDENTITY)
        self.assertEqual((o['rotY'], o['front']), (round(math.pi / 2, 4), [1, 0]))

    def test_front_ignores_the_object_position(self):
        o = b2r.convert_object(box(5, 0, 5), translation(1, 1, 1))
        self.assertEqual((o['rotY'], o['front']), (0, [0, 1]))


class PhotoTests(unittest.TestCase):
    def photo(self, room=0, blur=None, yaw=0.0, x=0.0):
        p = {'file': 'photos/0001.jpg', 'room': room, 'transform': pose(x, 1.5, 0, yaw),
             'intrinsics': [1000, 0, 0, 0, 1000, 0, 0, 0, 1], 'width': 2000, 'height': 1500}
        if blur is not None:
            p['blurPixels'] = blur
        return p

    def test_all_photos_are_kept_without_room_selection(self):
        photos = [self.photo(1), self.photo(0)]
        self.assertEqual(b2r.room_photos(photos, None), photos)

    def test_room_selection_keeps_that_room_in_order(self):
        photos = [self.photo(1), self.photo(0), self.photo(1, blur=2)]
        self.assertEqual(b2r.room_photos(photos, 1), [photos[0], photos[2]])

    def test_room_zero_is_a_selection(self):
        photos = [self.photo(1), self.photo(0)]
        self.assertEqual(b2r.room_photos(photos, 0), [photos[1]])

    def test_camera_looks_along_minus_z_with_up_along_minus_x(self):
        p = b2r.convert_photo(self.photo(x=2.123456), translation(-2, -1, 0))
        self.assertEqual((p['file'], p['position'], p['forward'], p['up']),
                         ('photos/0001.jpg', [0.1235, 0.5, 0], [0, 0, -1], [-1, 0, 0]))

    def test_directions_are_rounded_to_five_digits(self):
        p = b2r.convert_photo(self.photo(yaw=0.1), IDENTITY)
        self.assertEqual(p['up'], [round(-math.cos(0.1), 5), 0, round(-math.sin(0.1), 5)])

    def test_vertical_fov_spans_the_sensor_width(self):
        self.assertEqual(b2r.convert_photo(self.photo(), IDENTITY)['fovY'], 90.0)

    def test_fov_and_aspect_are_rounded(self):
        p = self.photo()
        p['width'], p['height'] = 1000, 777
        converted = b2r.convert_photo(p, IDENTITY)
        self.assertEqual(converted['fovY'], round(math.degrees(2 * math.atan(0.5)), 3))
        self.assertEqual(converted['aspect'], 0.777)

    def test_aspect_is_height_over_width(self):
        self.assertEqual(b2r.convert_photo(self.photo(), IDENTITY)['aspect'], 0.75)

    def test_blur_is_passed_through_when_measured(self):
        self.assertEqual(b2r.convert_photo(self.photo(blur=1.5), IDENTITY)['blurPixels'], 1.5)
        self.assertIsNone(b2r.convert_photo(self.photo(), IDENTITY)['blurPixels'])


class ConvertRoomTests(unittest.TestCase):
    def room(self):
        # Walls span x in [0, 4], z in [0, 2] on a floor at y = 0.1.
        return {'walls': [wall('s', 2, 0, 0, 4, bottom=0.1), wall('n', 2, 2, 0, 4, bottom=0.1),
                          wall('w', 0, 1, math.pi / 2, 2, bottom=0.1), wall('e', 4, 1, math.pi / 2, 2, bottom=0.1)],
                'objects': [box(2, 0.6, 1)]}

    def test_room_is_centered_on_its_floor(self):
        r = b2r.convert_room(self.room(), [], 'src')
        self.assertEqual(r['objects'][0]['center'], [0, 0.5, 0])
        self.assertEqual(r['transform']['center'], [2, 1])
        self.assertAlmostEqual(r['transform']['floorY'], 0.1)
        self.assertAlmostEqual(r['transform']['theta'], 0)

    def test_world_to_room_is_written_column_major(self):
        r = b2r.convert_room(self.room(), [], 'src')
        assert_close(self, r['transform']['worldToRoom'][12:15], [-2, -0.1, -1])

    def test_document_lists_source_polygon_walls_objects_and_photos(self):
        r = b2r.convert_room(self.room(), [PhotoTests.photo(PhotoTests())], 'src')
        self.assertEqual(list(r), ['source', 'transform', 'polygon', 'walls', 'objects', 'photos'])
        self.assertEqual((r['source'], r['polygon']), ('src', None))
        self.assertEqual([w['index'] for w in r['walls']], [0, 1, 2, 3])
        self.assertEqual(len(r['photos']), 1)

    def test_turn_rotates_the_room_a_quarter(self):
        r = b2r.convert_room(self.room(), [], 'src', turn=1)
        self.assertAlmostEqual(r['transform']['theta'], -math.pi / 2)
        # World -z now points along room +x, so the south wall lands on x = +1.
        assert_close(self, r['walls'][0]['a'], [1, -2])
        assert_close(self, r['walls'][0]['b'], [1, 2])

    def test_openings_reach_their_wall(self):
        room = self.room()
        room['doors'] = [{'parentIdentifier': 'n', 'transform': pose(2, 1.1, 2, 0),
                          'dimensions': [1, 2, 0], 'category': {'door': {}}}]
        r = b2r.convert_room(room, [], 'src')
        self.assertEqual([len(w['openings']) for w in r['walls']], [0, 1, 0, 0])

    def test_room_without_objects_has_an_empty_list(self):
        room = self.room()
        del room['objects']
        self.assertEqual(b2r.convert_room(room, [], 'src')['objects'], [])


class SourceNameTests(unittest.TestCase):
    def test_bundle_folder_names_the_whole_structure(self):
        self.assertEqual(b2r.source_name('captures/kitchen/', None), 'kitchen')

    def test_room_index_is_appended_even_for_room_zero(self):
        self.assertEqual(b2r.source_name('kitchen', 0), 'kitchen room 0')


class SummaryTests(unittest.TestCase):
    def result(self):
        door = {'kind': 'door', 'u0': 0.5, 'u1': 1.25, 'v0': 0.0, 'v1': 2.0}
        window = {'kind': 'window', 'u0': 2.0, 'u1': 3.0, 'v0': 1.0, 'v1': 2.0}
        return {'walls': [
            {'index': 0, 'a': [-2, -1], 'b': [2, -1], 'length': 4, 'height': 2.5, 'n': [0, 0, 1], 'openings': [door, window]},
            {'index': 11, 'a': [2, 1.5], 'b': [-2, 1.5], 'length': 4, 'height': 2.1, 'n': [0, 0, -1], 'openings': []},
        ], 'objects': [{'category': 'sofa', 'center': [0.5, 0.4, -0.25], 'size': [2, 1, 1], 'rotY': math.pi / 2}],
            'photos': [{}, {}, {}]}

    def test_first_line_gives_extent_heights_counts_and_output(self):
        self.assertEqual(b2r.summary(self.result(), 'out.json')[0],
                         'room 4.00 × 2.50 m, heights [2.1, 2.5], 2 walls, 1 objects, 3 photos → out.json')

    def test_one_line_per_wall_lists_its_openings(self):
        lines = b2r.summary(self.result(), 'o')
        self.assertEqual(lines[1], '  wall  0: ( -2.00, -1.00) → (  2.00, -1.00)  len 4.00 h 2.50  n (0,1)  '
                                   'door u0.50-1.25 v0.00-2.00, window u2.00-3.00 v1.00-2.00')
        self.assertEqual(lines[2], '  wall 11: (  2.00,  1.50) → ( -2.00,  1.50)  len 4.00 h 2.10  n (0,-1)  ')

    def test_one_line_per_object_gives_its_turn_in_degrees(self):
        self.assertEqual(b2r.summary(self.result(), 'o')[3],
                         '  sofa         center (0.50,-0.25) size [2, 1, 1] rotY 90°')


class PlanTests(unittest.TestCase):
    PPM = 100

    def draw(self, result):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'plan.png'
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                b2r.plan(result, path, ppm=self.PPM)
            self.assertEqual(printed.getvalue(), f'{path}\n')
            with Image.open(path) as image:
                return image.convert('RGB').copy()

    def result(self, height=2.5, openings=()):
        return {'walls': [{'index': 0, 'a': [0, 0], 'b': [2, 0], 'u': [1, 0, 0], 'n': [0, 0, 1], 'length': 2,
                           'height': height, 'openings': list(openings)}], 'objects': [], 'photos': []}

    def pixel(self, image, x, z):
        # The plan frames the walls with half a metre on every side.
        return image.getpixel((int((x + 0.5) * self.PPM), int((z + 0.5) * self.PPM)))

    def test_plan_frames_the_walls_with_half_a_metre_margin(self):
        self.assertEqual(self.draw(self.result()).size, (300, 100))

    def test_tall_and_short_walls_are_drawn_in_different_colors(self):
        self.assertEqual(self.pixel(self.draw(self.result(2.5)), 0.75, 0), (235, 235, 235))
        self.assertEqual(self.pixel(self.draw(self.result(2.1)), 0.75, 0), (150, 150, 255))

    def test_doors_and_other_openings_are_drawn_over_their_wall(self):
        door = {'kind': 'door', 'u0': 0.2, 'u1': 0.8}
        window = {'kind': 'window', 'u0': 1.2, 'u1': 1.8}
        image = self.draw(self.result(openings=[door, window]))
        self.assertEqual(self.pixel(image, 0.65, 0), (80, 200, 255))
        self.assertEqual(self.pixel(image, 1.65, 0), (120, 255, 160))


class MainTests(unittest.TestCase):
    def test_main_writes_room_json_next_to_the_bundle_and_prints_the_summary(self):
        import synthetic_bundle
        with tempfile.TemporaryDirectory() as temp:
            bundle = synthetic_bundle.write_bundle(Path(temp) / 'b', rooms={1: synthetic_bundle.room_plan()})
            with mock.patch.object(sys, 'argv', ['bundle_to_room.py', str(bundle), '--room', '1']), \
                    contextlib.redirect_stdout(io.StringIO()) as printed:
                b2r.main()
            room = json.loads((bundle / 'room.json').read_text())
        self.assertEqual(room['source'], 'b room 1')
        self.assertEqual([p['file'] for p in room['photos']], ['photos/0001.jpg', 'photos/0003.jpg'])
        self.assertEqual(printed.getvalue().splitlines(), b2r.summary(room, str(bundle / 'room.json')))


if __name__ == '__main__':
    unittest.main()
