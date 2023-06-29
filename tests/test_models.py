import asyncio
import os
import tempfile
import unittest

from nanome.api import structure
from unittest.mock import MagicMock, patch
from iotbx.data_manager import DataManager
from iotbx.map_manager import map_manager
from iotbx.map_model_manager import map_model_manager

from mmtbx.model.model import manager
from plugin.models import MapGroup, MapMesh

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
        self.plugin = MagicMock()
        self.map_group = MapGroup(self.plugin)
        self.pdb_file = os.path.join(fixtures_dir, '7c4u.pdb')
        self.map_file = os.path.join(fixtures_dir, 'emd_30288.map.gz')

        shapes_mock = asyncio.Future()
        shapes_mock.set_result([MagicMock(), MagicMock()])
        self.plugin.client.shapes_upload_multiple = MagicMock(return_value=shapes_mock)

    def test_add_pdb(self):
        self.map_group.add_pdb(self.pdb_file)
        self.assertTrue(isinstance(self.map_group._model, manager))

    def test_add_map_gz(self):
        async def validate_add_map_gz(self):
            # Set future result for request_complexes mock
            fut = asyncio.Future()
            fut.set_result([structure.Complex()])
            self.plugin.client.add_to_workspace.return_value = fut
            # run add_map_gz, and make sure map_manager is created on internal map_manager
            self.assertTrue(isinstance(self.map_group.map_mesh.map_manager, type(None)))
            await self.map_group.add_map_gz(self.map_file)
            self.assertTrue(isinstance(self.map_group.map_mesh.map_manager, map_manager))
        run_awaitable(validate_add_map_gz, self)

    @patch('nanome._internal.network.PluginNetwork._instance', return_value=asyncio.Future())
    def test_generate_full_mesh(self, instance_mock):
        # Assert that attributes are set after load_map called.
        async def validate_generate_full_mesh(self):
            fut = asyncio.Future()
            fut.set_result([structure.Complex()])
            self.plugin.client.add_to_workspace.return_value = fut

            map_file = os.path.join(fixtures_dir, 'emd_30288.map.gz')
            expected_vertices = 14735
            # Make sure vertices are added to mesh
            self.assertEqual(len(self.map_group.map_mesh.computed_vertices), 0)
            await self.map_group.add_map_gz(map_file)
            await self.map_group.generate_full_mesh()
            self.assertEqual(len(self.map_group.map_mesh.computed_vertices), expected_vertices)
        run_awaitable(validate_generate_full_mesh, self)

    def test_generate_histogram(self):
        # Assert that attributes are set after load_map called.
        async def validate_generate_histogram(self):
            fut = asyncio.Future()
            fut.set_result([structure.Complex()])
            self.plugin.client.add_to_workspace.return_value = fut

            map_file = os.path.join(fixtures_dir, 'emd_30288.map.gz')
            await self.map_group.add_map_gz(map_file)
            await self.map_group.generate_full_mesh()
            with tempfile.TemporaryDirectory() as tmpdir:
                png_file = self.map_group.generate_histogram(tmpdir)
                self.assertTrue(os.path.exists(png_file))
        run_awaitable(validate_generate_histogram, self)


class MapMeshTestCase(unittest.TestCase):

    def setUp(self) -> None:
        super().setUp()
        self.plugin = MagicMock()
        self.pdb_file = os.path.join(fixtures_dir, '7c4u.pdb')
        self.map_file = os.path.join(fixtures_dir, 'emd_30288.map.gz')
        self.map_mesh = MapMesh(self.plugin)

        dm = DataManager()
        model = dm.get_model(self.pdb_file)
        self.map_manager = self.map_mesh.load_map_file(self.map_file)
        self.map_model_manager = map_model_manager(model=model, map_manager=self.map_manager)

        fut = asyncio.Future()
        fut.set_result([structure.Complex()])
        self.plugin.client.add_to_workspace.return_value = fut

    def test_add_map_gz_file(self):
        # Set future result for request_complexes mock
        fut = asyncio.Future()
        fut.set_result([structure.Complex()])
        self.plugin.client.add_to_workspace.return_value = fut
        # run add_map_gz, and make sure map_manager is created on internal map_manager
        self.assertTrue(isinstance(self.map_mesh.map_manager, type(None)))
        self.map_mesh.add_map_gz_file(self.map_file)
        self.assertTrue(isinstance(self.map_mesh.map_manager, map_manager))

    def test_load(self):
        """Validate that running load() generates the MapMesh.
        """
        async def validate_load(self):
            expected_vertices = 285798
            expected_normals = 537129
            expected_triangles = 537129
            isovalue = 0.2
            opacity = 0.65

            fut = asyncio.Future()
            fut.set_result([structure.Complex()])
            self.plugin.client.add_to_workspace.return_value = fut

            self.map_mesh.add_map_gz_file(self.map_file)

            mesh = self.map_mesh.mesh
            self.assertEqual(len(mesh.vertices), 0)
            self.assertEqual(len(mesh.normals), 0)
            self.assertEqual(len(mesh.triangles), 0)
            await self.map_mesh.load(self.map_manager, isovalue, opacity)
            mesh = self.map_mesh.mesh
            self.assertEqual(len(mesh.vertices), expected_vertices)
            self.assertEqual(len(mesh.normals), expected_normals)
            self.assertEqual(len(mesh.triangles), expected_triangles)
        run_awaitable(validate_load, self)

    def test_load_selected_residues(self):
        """Validate that running load() generates the MapMesh."""
        async def validate_load_selected_residues(self):
            map_file = os.path.join(fixtures_dir, 'emd_30288.map.gz')
            expected_vertices = 3255
            expected_normals = 3255
            expected_triangles = 5976
            self.map_mesh.add_map_gz_file(map_file)
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
        run_awaitable(validate_load_selected_residues, self)
