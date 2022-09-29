import asyncio
import os
import tempfile
import unittest
from iotbx.data_manager import DataManager
from iotbx.map_model_manager import map_model_manager
from nanome.api.shapes import Mesh
from nanome.api.structure import Complex
from nanome.util import enums

from plugin.models import MapGroup


fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')


def run_awaitable(awaitable, *args, **kwargs):
    loop = asyncio.get_event_loop()
    if loop.is_running:
        loop = asyncio.new_event_loop()
    result = loop.run_until_complete(awaitable(*args, **kwargs))
    loop.close()
    return result


class MapModelManagerTestCase(unittest.TestCase):

    def setUp(self):
        self.pdb_file = os.path.join(fixtures_dir, '7c4u.pdb')
        self.map_file = os.path.join(fixtures_dir, 'emd_30288.map.gz')
        self.comp = Complex.io.from_pdb(path=self.pdb_file)

    def test_map_model_manager(self):
        dm = DataManager()
        dm.set_overwrite(True)
        mm = dm.get_real_map(self.map_file)
        model = dm.get_model(self.pdb_file)
        mmm = map_model_manager(
            model=model,
            map_manager=mm
        )
        res_range = '201:210'
        box_mmm = mmm.extract_all_maps_around_model(selection_string=f'resseq {res_range}')
        # Write boxed residue range to files
        with tempfile.TemporaryDirectory() as dirname:
            boxed_map_filename = os.path.join(dirname, os.path.basename(self.map_file))
            boxed_model_filename = os.path.join(dirname, os.path.basename(self.pdb_file))
            # dm.write_real_map_file(mm, filename=boxed_map_filename)
            # dm.write_model_file(model, filename=boxed_model_filename, extension="pdb")
            dm.write_real_map_file(
                box_mmm.map_manager(),
                filename=boxed_map_filename)
            dm.write_model_file(
                box_mmm.model(),
                filename=boxed_model_filename,
                extension="pdb")
            self.assertTrue(os.path.exists(boxed_map_filename))
            self.assertTrue(os.path.exists(boxed_model_filename))
            pass


class MapGroupTestCase(unittest.TestCase):

    def setUp(self):
        self.map_group = MapGroup()
        self.pdb_file = os.path.join(fixtures_dir, '7c4u.pdb')
        self.map_file = os.path.join(fixtures_dir, 'emd_30288.map.gz')

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
    """Load map once, and test different settings."""

    @classmethod
    def setUpClass(cls):
        cls.map_group = MapGroup()
        cls.pdb_file = os.path.join(fixtures_dir, '7q1u.pdb')
        cls.map_gz_file = os.path.join(fixtures_dir, 'emd_30288.map.gz')
        cls.map_group.add_file(cls.pdb_file)
        cls.map_group.add_file(cls.map_gz_file)
        isovalue = 0.5
        opacity = 0.65
        color_scheme = enums.ColorScheme.BFactor
        cls.map_group.generate_mesh(isovalue, color_scheme, opacity)

    def test_generate_mesh(self):
        # Make sure setUpClass generated a mesh
        mesh = self.map_group.mesh
        self.assertTrue(isinstance(mesh, Mesh))

    def test_toggle_wireframe_mode(self):
        # wireframe_mode = self.map_group.wireframe_mode
        self.assertEqual(self.map_group.wireframe_mode, False)
        self.map_group.toggle_wireframe_mode(True)
        self.assertEqual(self.map_group.wireframe_mode, True)
        self.map_group.toggle_wireframe_mode(False)
        self.assertEqual(self.map_group.wireframe_mode, False)
