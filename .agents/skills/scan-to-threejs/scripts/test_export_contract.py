"""The house-capture/5 export contract, checked from the reading side.

The schema (apps/house-capture/schema/house-capture-5.schema.json) is authoritative. The
reference export next to it is what the iPhone app writes: the app's ExportContractTests
compare its own output to it. Here we check that the reference satisfies the schema and that
the Mac scripts read it.
"""
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import jsonschema

def schema_dir():
    # Walk up rather than counting levels: mutation testing runs this file from a copy.
    for folder in Path(__file__).resolve().parents:
        candidate = folder / 'apps/house-capture/schema'
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError('apps/house-capture/schema not found above ' + __file__)


SCHEMA_DIR = schema_dir()
FIXTURE = SCHEMA_DIR / 'fixture'
SCRIPTS = Path(__file__).resolve().parent


def load(path):
    return json.loads(Path(path).read_text())


class ExportContractTests(unittest.TestCase):
    def setUp(self):
        self.schema = load(SCHEMA_DIR / 'house-capture-5.schema.json')

    def validate(self, document, definition):
        jsonschema.validate(document, {**self.schema, '$ref': f'#/$defs/{definition}'})

    def test_reference_manifest_satisfies_the_schema(self):
        self.validate(load(FIXTURE / 'manifest.json'), 'manifest')

    def test_reference_photo_index_satisfies_the_schema(self):
        self.validate(load(FIXTURE / 'photos/photos.json'), 'photos')

    def test_reference_depth_index_satisfies_the_schema(self):
        self.validate(load(FIXTURE / 'depth/frames.json'), 'depthFrames')

    def test_a_photo_without_its_pose_is_rejected(self):
        photos = load(FIXTURE / 'photos/photos.json')
        del photos[0]['transform']
        with self.assertRaises(jsonschema.ValidationError):
            self.validate(photos, 'photos')

    def test_the_converter_reads_the_reference_photos(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / 'bundle'
            shutil.copytree(FIXTURE, bundle)
            wall = {'identifier': 'w', 'transform': [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 1.2, 0, 1],
                    'dimensions': [2, 2.4, 0], 'confidence': {'high': {}}}
            (bundle / 'rooms').mkdir()
            (bundle / 'rooms/room-0.json').write_text(json.dumps({'walls': [wall], 'objects': []}))
            out = Path(temp) / 'room.json'
            subprocess.run([sys.executable, str(SCRIPTS / 'bundle_to_room.py'), str(bundle), '--room', '0', '-o', str(out)],
                           check=True, capture_output=True)
            photos = load(out)['photos']
        self.assertEqual([p['file'] for p in photos], ['photos/0000.jpg'])
        self.assertAlmostEqual(photos[0]['fovY'], math.degrees(2 * math.atan(1920 / 2 / 1500)), places=2)


if __name__ == '__main__':
    unittest.main()
