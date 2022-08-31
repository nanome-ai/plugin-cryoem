import asyncio
import os
import unittest
from unittest.mock import MagicMock
from nanome.api.shapes import Mesh
from nanome.util import enums

from plugin.CryoEM import CryoEM
from plugin.models import MapGroup

fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')


def run_awaitable(awaitable, *args, **kwargs):
    loop = asyncio.get_event_loop()
    if loop.is_running:
        loop = asyncio.new_event_loop()
    result = loop.run_until_complete(awaitable(*args, **kwargs))
    loop.close()
    return result


class MapGroupTestCase(unittest.TestCase):
    
    def setUp(self):
        self.map_group = MapGroup()
        self.pdb_file = os.path.join(fixtures_dir, '7q1u.pdb')
        self.map_file = os.path.join(fixtures_dir, 'emd_13764.map.gz')

    def test_add_file_pdb(self):
        self.map_group.add_file(self.pdb_file)
        self.assertTrue(self.pdb_file in self.map_group.files)
    
    def test_add_file_map(self):
        self.map_group.add_file(self.map_file)
        self.assertTrue(self.map_file in self.map_group.files)
        self.assertTrue(self.map_file in self.map_group.files)
    
    def test_load_map(self):
        # Assert that attributes are set after load_map called.
        attrs_to_set = ['_map_data', '_map_voxel_size', '_map_origin']
        for attr in attrs_to_set:
            self.assertTrue(getattr(self.map_group, attr) is None)
        self.map_group.load_map(self.map_file)
        for attr in attrs_to_set:
            self.assertTrue(getattr(self.map_group, attr) is not None)


class LoadedMapGroupTestCase(unittest.TestCase):
    """Load map once and test different settings."""

    @classmethod
    def setUpClass(cls):
        cls.map_group = MapGroup()
        cls.pdb_file = os.path.join(fixtures_dir, '7q1u.pdb')
        cls.map_file = os.path.join(fixtures_dir, 'emd_13764.map.gz')
        cls.map_group.add_file(cls.pdb_file)
        cls.map_group.add_file(cls.map_file)
        isovalue = 0.5
        opacity = 0.65
        color_scheme = enums.ColorScheme.BFactor
        cls.map_group.generate_mesh(isovalue, color_scheme, opacity)

    def test_generate_mesh(self):
        mesh = self.map_group.mesh
        self.assertTrue(isinstance(mesh, Mesh))

    def test_toggle_wireframe_mode(self):
        breakpoint()
        # wireframe_mode = self.map_group.wireframe_mode
        self.assertEqual(self.map_group.wireframe_mode, False)
        self.map_group.toggle_wireframe_mode(True)
        self.assertEqual(self.map_group.wireframe_mode, True)
        self.map_group.toggle_wireframe_mode(False)
        self.assertEqual(self.map_group.wireframe_mode, False)
        # self.assertTrue(self.map_group.wireframe_mode)
        # self.assertFalse(self.map_group.wireframe_mode)
