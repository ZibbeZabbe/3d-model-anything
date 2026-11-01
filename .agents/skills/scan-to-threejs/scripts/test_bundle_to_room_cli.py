"""Characterization of the bundle_to_room.py command line on synthetic bundles.

The golden files in testdata/bundle_to_room/ were produced by the script itself and pin
its whole output: room.json and the printed summary. Regenerate them only on purpose:
    uv run python .agents/skills/scan-to-threejs/scripts/test_bundle_to_room_cli.py --regenerate
Floats are compared with a tight tolerance, since libm may differ in the last bit between
macOS and Linux; everything else, including int/float types and key order, must match.
"""
import json
import math
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

import synthetic_bundle

SCRIPTS = Path(__file__).resolve().parent
GOLDEN = SCRIPTS / 'testdata/bundle_to_room'
FLOAT_TOLERANCE = 1e-9
OUT_PLACEHOLDER = '<out>'
# '-0.00' and '0.00' differ only by the sign of a value below print precision.
NEGATIVE_ZERO = re.compile(r'-(0(?:\.0+)?)(?![\d])')


def scenarios():
    """name -> (bundle builder kwargs, extra CLI arguments, output file name or None)."""
    return {
        'structure': ({'structure': synthetic_bundle.room_plan()}, [], None),
        'room-turned': ({'rooms': {1: synthetic_bundle.room_plan(floor=False)}},
                        ['--room', '1', '--turn', '1'], 'turned.json'),
        'room-no-corners': ({'rooms': {0: synthetic_bundle.room_plan(corners=False)},
                             'with_photos': False},
                            ['--room', '0', '--plan', 'PLAN'], 'plain.json'),
    }


def run(name, temp):
    """Run the CLI on one scenario; return (room.json text, normalized stdout, plan path)."""
    kwargs, extra, out_name = scenarios()[name]
    bundle = synthetic_bundle.write_bundle(Path(temp) / 'synthetic-bundle', **kwargs)
    plan = Path(temp) / 'plan.png'
    args = [str(plan) if a == 'PLAN' else a for a in extra]
    out = Path(temp) / out_name if out_name else bundle / 'room.json'
    if out_name:
        args += ['-o', str(out)]
    result = subprocess.run([sys.executable, str(SCRIPTS / 'bundle_to_room.py'), str(bundle), *args],
                            check=True, capture_output=True, text=True)
    stdout = result.stdout.replace(str(Path(temp)), OUT_PLACEHOLDER)
    return out.read_text(), stdout, plan


def assert_same(test, actual, expected, where='$'):
    test.assertIs(type(actual), type(expected), where)
    if isinstance(expected, float):
        test.assertTrue(math.isclose(actual, expected, rel_tol=FLOAT_TOLERANCE, abs_tol=FLOAT_TOLERANCE),
                        f'{where}: {actual!r} != {expected!r}')
    elif isinstance(expected, dict):
        test.assertEqual(list(actual), list(expected), where)
        for key in expected:
            assert_same(test, actual[key], expected[key], f'{where}.{key}')
    elif isinstance(expected, list):
        test.assertEqual(len(actual), len(expected), where)
        for i, (a, e) in enumerate(zip(actual, expected)):
            assert_same(test, a, e, f'{where}[{i}]')
    else:
        test.assertEqual(actual, expected, where)


class BundleToRoomCliTests(unittest.TestCase):
    def check(self, name):
        with tempfile.TemporaryDirectory() as temp:
            room, stdout, _ = run(name, temp)
        assert_same(self, json.loads(room), json.loads((GOLDEN / f'{name}.room.json').read_text()))
        expected = (GOLDEN / f'{name}.stdout.txt').read_text()
        self.assertEqual(NEGATIVE_ZERO.sub(r'\1', stdout), NEGATIVE_ZERO.sub(r'\1', expected))

    def test_whole_structure_converts_to_the_pinned_room(self):
        self.check('structure')

    def test_one_room_turned_a_quarter_without_floor_converts_to_the_pinned_room(self):
        self.check('room-turned')

    def test_room_with_floor_but_no_corners_converts_to_the_pinned_room(self):
        self.check('room-no-corners')

    def test_plan_option_writes_an_image_framing_the_walls_with_a_margin(self):
        with tempfile.TemporaryDirectory() as temp:
            _, _, plan = run('room-no-corners', temp)
            with Image.open(plan) as image:
                self.assertEqual(image.size, tuple(json.loads((GOLDEN / 'room-no-corners.plan-size.json').read_text())))


def regenerate():
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for name in scenarios():
        with tempfile.TemporaryDirectory() as temp:
            room, stdout, plan = run(name, temp)
            (GOLDEN / f'{name}.room.json').write_text(room)
            (GOLDEN / f'{name}.stdout.txt').write_text(stdout)
            if plan.exists():
                with Image.open(plan) as image:
                    (GOLDEN / f'{name}.plan-size.json').write_text(json.dumps(list(image.size)) + '\n')


if __name__ == '__main__':
    if '--regenerate' in sys.argv:
        regenerate()
    else:
        unittest.main()
