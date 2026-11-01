"""Behaviour of prepare_photos: upright JPEGs numbered in the converted room's photo order."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image

import prepare_photos

DEFAULT_MAX_EDGE = 1280
RED, BLUE = (255, 0, 0), (0, 0, 255)


def split_image(size, left=RED, right=BLUE, mode='RGB'):
    """Sensor-oriented image whose left half is `left` and right half `right`."""
    image = Image.new('RGB', size, right)
    image.paste(left, (0, 0, size[0] // 2, size[1]))
    return image.convert(mode)


class PhotoBundle(unittest.TestCase):
    """A bundle folder and a converted room JSON in a temporary directory."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.bundle = self.base / 'bundle'
        (self.bundle / 'photos').mkdir(parents=True)
        self.room = self.base / 'room.json'

    def tearDown(self):
        self.temp.cleanup()

    def photos(self, *images, files=None):
        names = files or [f'photos/{i:04d}.png' for i in range(len(images))]
        for name, image in zip(names, images):
            image.save(self.bundle / name)
        self.room.write_text(json.dumps({'photos': [{'file': name} for name in names]}))

    def run_prepare(self, out=None, **kwargs):
        return prepare_photos.prepare(self.bundle, self.room, out or self.base / 'out', **kwargs)


class PrepareTests(PhotoBundle):

    def test_sensor_left_becomes_the_top_of_the_upright_image(self):
        self.photos(split_image((40, 20)))
        self.run_prepare()
        with Image.open(self.base / 'out/0000.jpg') as upright:
            self.assertEqual(upright.size, (20, 40))
            top, bottom = upright.getpixel((10, 5)), upright.getpixel((10, 35))
        self.assertGreater(top[0], 200)
        self.assertGreater(bottom[2], 200)

    def test_files_are_numbered_in_room_order_and_counted(self):
        self.photos(Image.new('RGB', (8, 4), RED), Image.new('RGB', (8, 4), BLUE),
                    files=['photos/0007.png', 'photos/0002.png'])
        self.assertEqual(self.run_prepare(), 2)
        self.assertEqual(sorted(os.listdir(self.base / 'out')), ['0000.jpg', '0001.jpg'])
        with Image.open(self.base / 'out/0001.jpg') as second:
            self.assertGreater(second.getpixel((2, 4))[2], 200)

    def test_long_edge_is_capped_at_1280_by_default(self):
        self.photos(Image.new('RGB', (3000, 1500)))
        self.run_prepare()
        with Image.open(self.base / 'out/0000.jpg') as upright:
            self.assertEqual(upright.size, (DEFAULT_MAX_EDGE // 2, DEFAULT_MAX_EDGE))

    def test_long_edge_is_capped_at_the_requested_size(self):
        self.photos(Image.new('RGB', (400, 200)))
        self.run_prepare(max_edge=100)
        with Image.open(self.base / 'out/0000.jpg') as upright:
            self.assertEqual(upright.size, (50, 100))

    def test_small_images_are_not_enlarged(self):
        self.photos(Image.new('RGB', (40, 20)))
        self.run_prepare(max_edge=100)
        with Image.open(self.base / 'out/0000.jpg') as upright:
            self.assertEqual(upright.size, (20, 40))

    def test_a_one_pixel_edge_is_allowed(self):
        self.photos(Image.new('RGB', (40, 20)))
        self.assertEqual(self.run_prepare(max_edge=1), 1)

    def test_a_zero_edge_is_rejected(self):
        self.photos(Image.new('RGB', (40, 20)))
        with self.assertRaisesRegex(ValueError, 'max-edge must be positive'):
            self.run_prepare(max_edge=0)
        self.assertFalse((self.base / 'out').exists())

    def test_transparent_and_grey_sources_become_rgb_jpegs(self):
        self.photos(split_image((8, 4), mode='RGBA'), split_image((8, 4), mode='L'))
        self.run_prepare()
        for name in ['0000.jpg', '0001.jpg']:
            with Image.open(self.base / 'out' / name) as upright:
                self.assertEqual((upright.format, upright.mode), ('JPEG', 'RGB'))

    def test_existing_output_is_refused_and_left_alone(self):
        self.photos(Image.new('RGB', (8, 4)))
        (self.base / 'out').mkdir()
        (self.base / 'out/keep.txt').write_text('mine')
        with self.assertRaisesRegex(ValueError, 'output directory exists'):
            self.run_prepare()
        self.assertEqual(os.listdir(self.base / 'out'), ['keep.txt'])

    def test_photo_outside_the_bundle_is_refused(self):
        Image.new('RGB', (8, 4)).save(self.base / 'secret.png')
        self.room.write_text(json.dumps({'photos': [{'file': '../secret.png'}]}))
        with self.assertRaisesRegex(ValueError, 'photo path escapes bundle'):
            self.run_prepare()
        self.assertFalse((self.base / 'out').exists())

    def test_bundle_given_through_dot_dot_still_contains_its_photos(self):
        self.photos(Image.new('RGB', (8, 4)))
        roundabout = self.bundle / 'photos' / '..'
        self.assertEqual(prepare_photos.prepare(roundabout, self.room, self.base / 'out'), 1)

    def test_a_missing_photo_leaves_no_partial_output(self):
        self.photos(Image.new('RGB', (8, 4)), files=['photos/0000.png'])
        self.room.write_text(json.dumps({'photos': [{'file': 'photos/0000.png'}, {'file': 'photos/gone.png'}]}))
        with self.assertRaises(OSError):
            self.run_prepare()
        self.assertFalse((self.base / 'out').exists())
        self.assertEqual(sorted(p.name for p in self.base.iterdir()), ['bundle', 'room.json'])

    def test_missing_parent_folders_of_the_output_are_created(self):
        self.photos(Image.new('RGB', (8, 4)))
        self.run_prepare(out=self.base / 'a/b/out')
        self.assertEqual(os.listdir(self.base / 'a/b/out'), ['0000.jpg'])


class MainTests(PhotoBundle):
    def main(self, *args):
        argv = ['prepare_photos.py', str(self.bundle), str(self.room), str(self.base / 'out'), *args]
        with mock.patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()) as printed, \
                contextlib.redirect_stderr(io.StringIO()) as errors:
            try:
                prepare_photos.main()
            except SystemExit as stop:
                return stop.code, printed.getvalue(), errors.getvalue()
        return 0, printed.getvalue(), errors.getvalue()

    def test_main_prints_how_many_photos_it_wrote(self):
        self.photos(Image.new('RGB', (8, 4)), Image.new('RGB', (8, 4)))
        code, printed, _ = self.main()
        self.assertEqual((code, printed), (0, f'2 photos → {self.base / "out"}\n'))

    def test_main_passes_the_max_edge_option(self):
        self.photos(Image.new('RGB', (400, 200)))
        self.main('--max-edge', '10')
        with Image.open(self.base / 'out/0000.jpg') as upright:
            self.assertEqual(upright.size, (5, 10))

    def test_main_reports_a_refusal_as_a_usage_error(self):
        self.photos(Image.new('RGB', (8, 4)))
        code, _, errors = self.main('--max-edge', '0')
        self.assertEqual(code, 2)
        self.assertIn('max-edge must be positive', errors)


if __name__ == '__main__':
    unittest.main()
