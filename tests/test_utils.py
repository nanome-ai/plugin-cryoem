import os
import unittest

from plugin.utils import EMDBMetadataParser


fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')


class EMDBMetadataParserTestCase(unittest.TestCase):

    def setUp(self):
        self.metadata_file = os.path.join(fixtures_dir, 'metadata_8216.xml')
        metadata_str = open(self.metadata_file).read()
        self.parser = EMDBMetadataParser(metadata_str)

    def test_isovalue(self):
        expected_value = 0.2
        self.assertEqual(self.parser.isovalue, expected_value)

    def test_resolution(self):
        expected_value = 1.1
        self.assertEqual(self.parser.resolution, expected_value)

    def test_map_filesize(self):
        expected_value = 1661
        self.assertEqual(self.parser.map_filesize, expected_value)
