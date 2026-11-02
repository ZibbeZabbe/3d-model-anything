"""Behaviour of house_to_rooms: rigid-transform checks and the house export index."""
import contextlib
import copy
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from bundle_to_room import apply, flatten, mat, mul
import house_to_rooms
from house_to_rooms import child, export_house, inverse_rigid, keyed, rigid
from synthetic_bundle import pose

IDENTITY = flatten([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
ALIGNED_METHODS = ['first', 'relocalized', 'manual', 'icp']


def general_rotation(x=0.0, y=0.0, z=0.0):
    """Rigid transform turned about all three axes, so every matrix entry is non-zero."""
    a, b, c = 0.3, 0.7, 1.1
    rx = [[1, 0, 0, 0], [0, math.cos(a), -math.sin(a), 0], [0, math.sin(a), math.cos(a), 0], [0, 0, 0, 1]]
    ry = [[math.cos(b), 0, math.sin(b), 0], [0, 1, 0, 0], [-math.sin(b), 0, math.cos(b), 0], [0, 0, 0, 1]]
    rz = [[math.cos(c), -math.sin(c), 0, 0], [math.sin(c), math.cos(c), 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    m = mul(rz, mul(ry, rx))
    m[0][3], m[1][3], m[2][3] = x, y, z
    return m


def with_entry(values, row, column, value):
    m = mat(values)
    m[row][column] = value
    return flatten(m)


class RigidTests(unittest.TestCase):
    def test_a_rigid_transform_comes_back_as_rows(self):
        values = flatten(general_rotation(1, 2, 3))
        self.assertEqual(rigid(values), mat(values))

    def test_integer_values_are_accepted(self):
        self.assertEqual(rigid([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 4, 5, 6, 1])[2][3], 6)

    def test_values_must_be_a_list_of_sixteen_numbers(self):
        for values in [tuple(IDENTITY), IDENTITY[:15], IDENTITY + [0], IDENTITY[:15] + ['1'],
                       IDENTITY[:15] + [True], IDENTITY[:15] + [None]]:
            with self.assertRaisesRegex(ValueError, r'^expected 16 finite column-major matrix values$'):
                rigid(values)

    def test_values_must_be_finite(self):
        for bad in [math.nan, math.inf, -math.inf]:
            with self.assertRaisesRegex(ValueError, r'^expected 16 finite column-major matrix values$'):
                rigid(with_entry(IDENTITY, 0, 3, bad))

    def test_last_row_must_be_affine(self):
        for column, value in [(0, 0.5), (1, 0.5), (2, 0.5), (3, 2), (3, 0)]:
            with self.assertRaisesRegex(ValueError, r'^expected an affine transform$'):
                rigid(with_entry(IDENTITY, 3, column, value))

    def test_last_row_tolerates_float_noise(self):
        noisy = with_entry(with_entry(IDENTITY, 3, 0, 5e-5), 3, 3, 1 - 5e-5)
        self.assertEqual(rigid(noisy)[3][3], 1 - 5e-5)

    def test_last_row_noise_above_the_tolerance_is_rejected(self):
        with self.assertRaisesRegex(ValueError, r'^expected an affine transform$'):
            rigid(with_entry(IDENTITY, 3, 2, 2e-4))

    def test_scale_is_rejected(self):
        for axis in range(3):
            with self.assertRaisesRegex(ValueError, r'^expected rigid rotation, without scale/shear$'):
                rigid(with_entry(IDENTITY, axis, axis, 1.1))

    def test_shear_is_rejected(self):
        for row, column in [(0, 1), (1, 2), (2, 0)]:
            with self.assertRaisesRegex(ValueError, r'^expected rigid rotation, without scale/shear$'):
                rigid(with_entry(IDENTITY, row, column, 0.1))

    def test_rotation_noise_within_the_tolerance_is_accepted(self):
        rigid(with_entry(IDENTITY, 0, 1, 4e-4))

    def test_rotation_noise_above_the_tolerance_is_rejected(self):
        with self.assertRaisesRegex(ValueError, r'^expected rigid rotation, without scale/shear$'):
            rigid(with_entry(IDENTITY, 0, 1, 2e-3))

    def test_a_mirrored_frame_is_rejected(self):
        for axis in range(3):
            mirrored = general_rotation()
            for row in range(3):
                mirrored[row][axis] = -mirrored[row][axis]
            with self.assertRaisesRegex(ValueError, r'^reflected coordinate frames are unsupported$'):
                rigid(flatten(mirrored))

    def test_inverse_undoes_a_rigid_transform(self):
        m = general_rotation(1, -2, 3)
        for product in (mul(inverse_rigid(m), m), mul(m, inverse_rigid(m))):
            for r in range(4):
                for c in range(4):
                    self.assertAlmostEqual(product[r][c], 1 if r == c else 0)

    def test_inverse_keeps_an_affine_last_row(self):
        inverse = inverse_rigid(general_rotation(1, 2, 3))
        self.assertEqual(len(inverse), 4)
        self.assertEqual(inverse[3], [0, 0, 0, 1])


class HelperTests(unittest.TestCase):
    def test_keyed_indexes_items_by_id(self):
        a, b = {'id': 'a', 'v': 1}, {'id': 'b'}
        self.assertEqual(keyed([a, b]), {'a': a, 'b': b})

    def test_keyed_rejects_duplicate_ids(self):
        with self.assertRaisesRegex(ValueError, r'^duplicate IDs in house metadata$'):
            keyed([{'id': 'a'}, {'id': 'a'}])

    def test_child_resolves_inside_the_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            self.assertEqual(child(root, 'a/../b/c.json'), root / 'b/c.json')

    def test_child_refuses_a_path_leaving_the_root(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, r'^path escapes house folder: \.\./x$'):
                child(Path(temp).resolve(), '../x')


def room_plan(x):
    """One wall and one table, centered on world x = `x`."""
    return {'walls': [{'identifier': 'w', 'transform': pose(x, 1, 0, 0), 'dimensions': [4, 2, 0],
                       'confidence': {'high': {}}}],
            'objects': [{'category': {'table': {}}, 'transform': pose(x, 0.5, 0.5, 0), 'dimensions': [1, 1, 1]}]}


class HouseFixture(unittest.TestCase):
    """A house folder with two zones, two sessions and two active rooms."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'house'
        self.out = self.base / 'export'
        for session, x in [('s1', 2), ('s2', -3)]:
            rooms = self.root / 'sessions' / session / 'rooms'
            rooms.mkdir(parents=True)
            for index in range(2):
                (rooms / f'room-{index}.json').write_text(json.dumps(room_plan(x + index)))
        self.zone_to_house = flatten(general_rotation(10, 0, 20))
        self.session_to_zone = pose(1, 0.5, -1, 0.4)
        self.house = {
            'format': 'house-project/1', 'id': 'home', 'name': 'Home',
            'zones': [{'id': 'z1', 'aligned': True, 'toHouse': self.zone_to_house},
                      {'id': 'z2', 'aligned': True, 'toHouse': IDENTITY}],
            'sessions': [{'id': 's1', 'zone': 'z1', 'alignment': {'method': 'manual', 'toZone': self.session_to_zone}},
                         {'id': 's2', 'zone': 'z2', 'alignment': {'method': 'first', 'toZone': IDENTITY}}],
            'rooms': [{'id': 'office', 'name': 'Office', 'zone': 'z1', 'active': {'session': 's1', 'index': 1}},
                      {'id': 'hall', 'name': 'Hall', 'zone': 'z2', 'active': {'session': 's2', 'index': 0}}],
        }

    def tearDown(self):
        self.temp.cleanup()

    def export(self, room_id=None):
        (self.root / 'house.json').write_text(json.dumps(self.house))
        return export_house(self.root, self.out, room_id)

    def office(self):
        return self.house['rooms'][0]

    def blocked_reason(self):
        entry = self.export()['rooms'][0]
        self.assertEqual(entry['status'], 'blocked')
        self.assertNotIn('file', entry)
        return entry['reason']


class ExportTests(HouseFixture):
    # --- house metadata --------------------------------------------------------

    def test_another_format_is_refused(self):
        self.house['format'] = 'house-project/2'
        with self.assertRaisesRegex(ValueError, r'^expected house-project/1$'):
            self.export()

    def test_duplicate_zone_session_or_room_ids_are_refused(self):
        for key in ['zones', 'sessions', 'rooms']:
            house = copy.deepcopy(self.house)
            house[key].append(copy.deepcopy(house[key][0]))
            (self.root / 'house.json').write_text(json.dumps(house))
            with self.assertRaisesRegex(ValueError, r'^duplicate IDs in house metadata$', msg=key):
                export_house(self.root, self.out)
        self.assertFalse(self.out.exists())

    def test_unknown_room_selection_is_refused_before_writing(self):
        with self.assertRaisesRegex(ValueError, r'^no matching rooms$'):
            self.export('attic')
        self.assertFalse(self.out.exists())

    def test_existing_output_is_refused(self):
        self.out.mkdir()
        with self.assertRaisesRegex(ValueError, r'^output directory already exists; choose a new output directory$'):
            self.export()

    def test_index_describes_the_house_and_its_source(self):
        index = self.export()
        self.assertEqual({k: v for k, v in index.items() if k != 'rooms'},
                         {'format': 'house-rebuild/1', 'house': 'home', 'name': 'Home',
                          'source': str(self.root), 'matrixOrder': 'column-major'})

    def test_source_is_the_resolved_house_folder(self):
        (self.root / 'house.json').write_text(json.dumps(self.house))
        index = export_house(self.root / 'sessions' / '..', self.out)
        self.assertEqual(index['source'], str(self.root))

    def test_index_is_written_as_indented_json_with_a_final_newline(self):
        index = self.export()
        self.assertEqual((self.out / 'index.json').read_text(), json.dumps(index, indent=2) + '\n')

    def test_output_holds_only_the_index_and_the_ready_rooms(self):
        self.export()
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ['index.json', 'room-000.json', 'room-001.json'])
        self.assertEqual(sorted(p.name for p in self.base.iterdir()), ['export', 'house'])

    def test_missing_parent_folders_of_the_output_are_created(self):
        self.out = self.base / 'a/b/export'
        self.export()
        self.assertTrue((self.out / 'index.json').is_file())

    # --- room selection and numbering ------------------------------------------

    def test_every_room_is_exported_in_house_order(self):
        index = self.export()
        self.assertEqual([(r['id'], r['status'], r['file']) for r in index['rooms']],
                         [('office', 'ready', 'room-000.json'), ('hall', 'ready', 'room-001.json')])

    def test_selection_exports_only_that_room(self):
        index = self.export('hall')
        self.assertEqual([(r['id'], r['file']) for r in index['rooms']], [('hall', 'room-000.json')])

    def test_blocked_rooms_keep_their_number(self):
        del self.office()['active']
        index = self.export()
        self.assertEqual(index['rooms'][1]['file'], 'room-001.json')
        self.assertFalse((self.out / 'room-000.json').exists())

    def test_entry_echoes_the_room_and_its_active_scan(self):
        entry = self.export()['rooms'][0]
        self.assertEqual({k: entry[k] for k in ['id', 'name', 'zone', 'active']},
                         {'id': 'office', 'name': 'Office', 'zone': 'z1', 'active': {'session': 's1', 'index': 1}})

    def test_entry_carries_the_level_the_room_was_put_on(self):
        self.office()['level'] = 1
        entry = self.export()['rooms'][0]
        self.assertEqual(entry['level'], 1)

    def test_a_room_without_a_level_says_so(self):
        entry = self.export()['rooms'][0]
        self.assertIsNone(entry['level'])

    # --- blocked rooms -----------------------------------------------------------

    def test_room_without_active_scan_is_blocked(self):
        del self.office()['active']
        entry = self.export()['rooms'][0]
        self.assertEqual((entry['status'], entry['reason'], entry['active']), ('blocked', 'no active scan', None))

    def test_unknown_session_is_blocked(self):
        self.office()['active']['session'] = 'ghost'
        self.assertEqual(self.blocked_reason(), "'ghost'")

    def test_session_from_another_zone_is_blocked(self):
        self.office()['zone'] = 'z2'
        self.assertEqual(self.blocked_reason(), 'active session belongs to a different zone')

    def test_unaligned_zone_is_blocked(self):
        self.house['zones'][0]['aligned'] = False
        self.assertEqual(self.blocked_reason(), 'zone placement is not aligned to the house')

    def test_zone_without_aligned_flag_is_blocked(self):
        del self.house['zones'][0]['aligned']
        self.assertEqual(self.blocked_reason(), 'zone placement is not aligned to the house')

    def test_every_alignment_method_places_the_room(self):
        for method in ALIGNED_METHODS:
            self.house['sessions'][0]['alignment']['method'] = method
            self.out = self.base / method
            self.assertEqual(self.export()['rooms'][0]['status'], 'ready', method)

    def test_session_still_to_align_is_blocked(self):
        self.house['sessions'][0]['alignment']['method'] = 'pending'
        self.assertEqual(self.blocked_reason(), 'session needs alignment: pending')

    def test_non_rigid_zone_placement_is_blocked(self):
        self.house['zones'][0]['toHouse'] = with_entry(IDENTITY, 0, 0, 2)
        self.assertEqual(self.blocked_reason(), 'expected rigid rotation, without scale/shear')

    def test_non_rigid_session_alignment_is_blocked(self):
        self.house['sessions'][0]['alignment']['toZone'] = with_entry(IDENTITY, 1, 1, 2)
        self.assertEqual(self.blocked_reason(), 'expected rigid rotation, without scale/shear')

    def test_room_index_must_be_a_non_negative_integer(self):
        for index in [-1, 1.0, True, '1', None]:
            self.office()['active']['index'] = index
            self.out = self.base / f'out-{index}'
            self.assertEqual(self.blocked_reason(), 'invalid active room index', index)

    def test_room_zero_is_a_valid_index(self):
        self.office()['active']['index'] = 0
        self.assertEqual(self.export()['rooms'][0]['status'], 'ready')

    def test_missing_room_scan_is_blocked_as_a_failed_conversion(self):
        self.office()['active']['index'] = 7
        reason = self.blocked_reason()
        self.assertTrue(reason.startswith('room conversion failed: '), reason)
        self.assertIn('room-7.json', reason)

    def test_room_whose_conversion_is_not_finite_leaves_no_file(self):
        broken = room_plan(0)
        broken['walls'][0]['transform'][12] = math.nan
        (self.root / 'sessions/s1/rooms/room-1.json').write_text(json.dumps(broken))
        self.assertEqual(self.blocked_reason(), 'expected 16 finite column-major matrix values')
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ['index.json', 'room-001.json'])

    # --- placement of ready rooms -----------------------------------------------

    def test_ready_entry_names_its_file_and_bundle(self):
        entry = self.export()['rooms'][0]
        self.assertEqual((entry['status'], entry['file'], entry['bundle']),
                         ('ready', 'room-000.json', str(self.root / 'sessions/s1')))
        self.assertNotIn('reason', entry)

    def test_room_file_is_the_converted_room_plus_its_placement(self):
        self.export()
        room = json.loads((self.out / 'room-000.json').read_text())
        self.assertEqual(room['source'], 's1 room 1')
        self.assertEqual(list(room)[-1], 'housePlacement')
        placement = room['housePlacement']
        self.assertEqual({k: placement[k] for k in ['house', 'zone', 'session', 'room', 'index']},
                         {'house': 'home', 'zone': 'z1', 'session': 's1', 'room': 'office', 'index': 1})

    def test_room_file_is_indented_json_with_a_final_newline(self):
        self.export()
        text = (self.out / 'room-000.json').read_text()
        self.assertEqual(text, json.dumps(json.loads(text), indent=2) + '\n')

    def test_session_to_house_chains_the_session_alignment_then_the_zone(self):
        self.export()
        placement = json.loads((self.out / 'room-000.json').read_text())['housePlacement']
        expected = mul(mat(self.zone_to_house), mat(self.session_to_zone))
        for actual, wanted in zip(placement['sessionToHouse'], flatten(expected)):
            self.assertAlmostEqual(actual, wanted)

    def test_room_to_house_places_room_points_where_the_scan_saw_them(self):
        index = self.export()
        room = json.loads((self.out / 'room-000.json').read_text())
        # The table of room 1 in session s1 stood at session (3, 0.5, 0.5).
        session_point = [3, 0.5, 0.5]
        expected = apply(mul(mat(self.zone_to_house), mat(self.session_to_zone)), session_point)
        actual = apply(mat(room['housePlacement']['roomToHouse']), room['objects'][0]['center'])
        for a, e in zip(actual, expected):
            self.assertAlmostEqual(a, e, places=3)
        self.assertEqual(index['rooms'][0]['roomToHouse'], room['housePlacement']['roomToHouse'])

    def test_source_bundles_and_house_file_are_left_unchanged(self):
        (self.root / 'house.json').write_text(json.dumps(self.house))
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        export_house(self.root, self.out)
        self.assertEqual({p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, before)


class MainTests(HouseFixture):
    def main(self, *args):
        (self.root / 'house.json').write_text(json.dumps(self.house))
        argv = ['house_to_rooms.py', str(self.root), '-o', str(self.out), *args]
        with mock.patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()) as printed, \
                contextlib.redirect_stderr(io.StringIO()) as errors:
            try:
                code = house_to_rooms.main()
            except SystemExit as stop:
                code = stop.code
        return code, printed.getvalue(), errors.getvalue()

    def test_main_succeeds_when_every_room_is_ready(self):
        code, printed, _ = self.main()
        self.assertEqual(code, 0)
        self.assertEqual(printed.splitlines(), ['ready: Office: room-000.json', 'ready: Hall: room-001.json',
                                                f'2/2 rooms ready; inspect {self.out / "index.json"}'])

    def test_main_signals_blocked_rooms_with_status_two(self):
        del self.office()['active']
        code, printed, _ = self.main()
        self.assertEqual(code, 2)
        self.assertEqual(printed.splitlines()[0], 'blocked: Office: no active scan')
        self.assertEqual(printed.splitlines()[-1], f'1/2 rooms ready; inspect {self.out / "index.json"}')

    def test_main_passes_the_room_selection(self):
        _, printed, _ = self.main('--room', 'hall')
        self.assertEqual(printed.splitlines()[0], 'ready: Hall: room-000.json')

    def test_main_reports_a_refused_export_as_a_usage_error(self):
        code, _, errors = self.main('--room', 'attic')
        self.assertEqual(code, 2)
        self.assertIn('no matching rooms', errors)


if __name__ == '__main__':
    unittest.main()
