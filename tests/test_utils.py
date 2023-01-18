import os
import unittest

from plugin.utils import EMDBMetadataParser


fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')


class EMDBMetadataParserTestCase(unittest.TestCase):

    def setUp(self):
        self.metadata_file = os.path.join(fixtures_dir, 'metadata_8216.xml')
        with open(self.metadata_file) as f:
            metadata_str = f.read()
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

    def test_pdb_list(self):
        expected_value = ['5k7n']
        pdb_list = self.parser.pdb_list
        self.assertEqual(pdb_list, expected_value)
