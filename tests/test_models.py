import asyncio
import gzip
import os
import tempfile
import unittest

from nanome.api import structure
from unittest.mock import MagicMock
from iotbx.data_manager import DataManager
from iotbx.map_manager import map_manager
from iotbx.map_model_manager import map_model_manager

from mmtbx.model.model import manager
from plugin.models import MapGroup, MapMesh

fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')


class MapGroupTestCase(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.plugin = MagicMock()
        self.map_group = MapGroup(self.plugin)
        self.pdb_file = os.path.join(fixtures_dir, '7c4u.pdb')
        self.mapgz_file = os.path.join(fixtures_dir, 'emd_8216.map.gz')

        shapes_mock = asyncio.Future()
        shapes_mock.set_result([MagicMock(), MagicMock()])
        self.plugin.client.shapes_upload_multiple = MagicMock(return_value=shapes_mock)

    def test_add_pdb(self):
        self.map_group.add_pdb(self.pdb_file)
        self.assertTrue(isinstance(self.map_group._model, manager))

    async def test_add_mapfile(self):
        # Set future result for request_complexes mock
        fut = asyncio.Future()
        fut.set_result([structure.Complex()])
        self.plugin.client.add_to_workspace.return_value = fut
        # run add_mapfile, and make sure map_manager is created on internal map_manager
        self.assertTrue(isinstance(self.map_group.map_mesh.map_manager, type(None)))
        await self.map_group.add_mapfile(self.mapgz_file)
        self.assertTrue(isinstance(self.map_group.map_mesh.map_manager, map_manager))

    async def test_generate_full_mesh(self):
        # Assert that attributes are set after load_map called.
        fut = asyncio.Future()
        fut.set_result([structure.Complex()])
        self.plugin.client.add_to_workspace.return_value = fut

        map_file = os.path.join(fixtures_dir, 'emd_8216.map.gz')
        expected_vertices = 14303
        # Make sure vertices are added to mesh
        self.assertEqual(len(self.map_group.map_mesh.computed_vertices), 0)
        await self.map_group.add_mapfile(map_file)
        await self.map_group.generate_full_mesh()
        self.assertEqual(len(self.map_group.map_mesh.computed_vertices), expected_vertices)

    async def test_generate_histogram(self):
        # Assert that attributes are set after load_map called.
        fut = asyncio.Future()
        fut.set_result([structure.Complex()])
        self.plugin.client.add_to_workspace.return_value = fut

        map_file = os.path.join(fixtures_dir, 'emd_8216.map.gz')
        await self.map_group.add_mapfile(map_file)
        await self.map_group.generate_full_mesh()
        with tempfile.TemporaryDirectory() as tmpdir:
            png_file = self.map_group.generate_histogram(tmpdir)
            self.assertTrue(os.path.exists(png_file))


class MapMeshTestCase(unittest.IsolatedAsyncioTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.plugin = MagicMock()
        self.pdb_file = os.path.join(fixtures_dir, '7c4u.pdb')
        self.mapgz_file = os.path.join(fixtures_dir, 'emd_8216.map.gz')
        self.map_mesh = MapMesh(self.plugin)

        dm = DataManager()
        model = dm.get_model(self.pdb_file)
        self.map_manager = self.map_mesh.load_mapfile(self.mapgz_file)
        self.map_model_manager = map_model_manager(
            model=model, map_manager=self.map_manager, ignore_symmetry_conflicts=True)

        fut = asyncio.Future()
        fut.set_result([structure.Complex()])
        self.plugin.client.add_to_workspace.return_value = fut

    def test_add_mapfile_mapgz(self):
        """Test that add_mapfile works with .map.gz files."""
        # Set future result for request_complexes mock
        fut = asyncio.Future()
        fut.set_result([structure.Complex()])
        self.plugin.client.add_to_workspace.return_value = fut
        # run add_mapfile, and make sure map_manager is created on internal map_manager
        self.assertTrue(isinstance(self.map_mesh.map_manager, type(None)))
        self.map_mesh.add_mapfile(self.mapgz_file)
        self.assertTrue(isinstance(self.map_mesh.map_manager, map_manager))

    def test_add_mapfile_map(self):
        """Test that add_mapfile works with .map files."""
        # Set future result for request_complexes mock
        fut = asyncio.Future()
        fut.set_result([structure.Complex()])
        self.plugin.client.add_to_workspace.return_value = fut
        with tempfile.NamedTemporaryFile(suffix='.map') as map_file:
            # Unzip map.gz to .map
            with gzip.open(self.mapgz_file, 'rb') as f:
                map_file.write(f.read())
            self.assertTrue(isinstance(self.map_mesh.map_manager, type(None)))
            self.map_mesh.add_mapfile(map_file.name)
            self.assertTrue(isinstance(self.map_mesh.map_manager, map_manager))

    async def test_load(self):
        """Validate that running load() generates the MapMesh.
        """
        expected_vertices = 37425
        expected_normals = 64008
        expected_triangles = 64008
        isovalue = 0.2
        opacity = 0.65

        fut = asyncio.Future()
        fut.set_result([structure.Complex()])
        self.plugin.client.add_to_workspace.return_value = fut

        self.map_mesh.add_mapfile(self.mapgz_file)

        mesh = self.map_mesh.mesh
        self.assertEqual(len(mesh.vertices), 0)
        self.assertEqual(len(mesh.normals), 0)
        self.assertEqual(len(mesh.triangles), 0)
        await self.map_mesh.load(self.map_manager, isovalue, opacity)
        mesh = self.map_mesh.mesh
        self.assertEqual(len(mesh.vertices), expected_vertices)
        self.assertEqual(len(mesh.normals), expected_normals)
        self.assertEqual(len(mesh.triangles), expected_triangles)

    async def test_load_selected_residues(self):
        """Validate that running load() generates the MapMesh."""
        map_file = os.path.join(fixtures_dir, 'emd_8216.map.gz')
        expected_vertices = 1305
        expected_normals = 1305
        expected_triangles = 1905
        self.map_mesh.add_mapfile(map_file)
        isovalue = 0.2
        opacity = 0.65

        model_comp = structure.Complex.io.from_pdb(path=self.pdb_file)
        fut = asyncio.Future()
        fut.set_result([model_comp])
        self.plugin.client.request_complexes.return_value = fut

        mesh = self.map_mesh.mesh
        self.assertEqual(len(mesh.vertices), 0)
        self.assertEqual(len(mesh.normals), 0)
        self.assertEqual(len(mesh.triangles), 0)

        selected_residues = list(model_comp.residues)[:3]
        await self.map_mesh.load(self.map_manager, isovalue, opacity, selected_residues)
        mesh = self.map_mesh.mesh

        self.assertEqual(len(mesh.vertices), expected_vertices)
        self.assertEqual(len(mesh.normals), expected_normals)
        self.assertEqual(len(mesh.triangles), expected_triangles)
