import asyncio
import os
import unittest
from nanome.api import structure
from unittest.mock import MagicMock, patch
from iotbx.map_manager import map_manager

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

    def test_add_pdb(self):
        self.map_group.add_pdb(self.pdb_file)
        self.assertTrue(isinstance(self.map_group._model, manager))

    def test_add_map_gz(self):
        async def validate_add_map_gz(self):
            # Set future result for request_complexes mock
            fut = asyncio.Future()
            fut.set_result([structure.Complex()])
            self.plugin.add_to_workspace.return_value = fut
            # run add_map_gz, and make sure map_manager is created on internal map_manager
            self.assertTrue(isinstance(self.map_group.map_mesh.map_manager, type(None)))
            await self.map_group.add_map_gz(self.map_file)
            self.assertTrue(isinstance(self.map_group.map_mesh.map_manager, map_manager))
        run_awaitable(validate_add_map_gz, self)

    @patch('nanome._internal._network.PluginNetwork._instance')
    @patch('nanome.api.plugin_instance.PluginInstance', return_value=asyncio.Future())
    @unittest.skip("Need to figure out mocking. =(")
    def test_generate_mesh(self, instance_mock, plugin_mock, *mocks):
        # Assert that attributes are set after load_map called.
        async def validate_generate_mesh(self):
            await self.map_group.add_map_gz(self.map_file)
            self.assertEqual(len(self.map_group.map_mesh.vertices), 0)
            await self.map_group.generate_mesh()
            self.assertTrue(len(self.map_group.map_mesh.computed_vertices) > 0)
        plugin_mock.add_to_workspace.return_value = asyncio.Future()
        with patch('plugin.models.MapGroup._plugin', plugin_mock):
            with patch('nanome.api.plugin_instance.PluginInstance._instance'):
                run_awaitable(validate_generate_mesh, self)
        # run_awaitable(validate_generate_mesh, self)

    # def test_toggle_wireframe_mode(self):
    #     # wireframe_mode = self.map_group.wireframe_mode
    #     self.assertEqual(self.map_group.wireframe_mode, False)
    #     self.map_group.toggle_wireframe_mode(True)
    #     self.assertEqual(self.map_group.wireframe_mode, True)
    #     self.map_group.toggle_wireframe_mode(False)
    #     self.assertEqual(self.map_group.wireframe_mode, False)


class MapMeshTestCase(unittest.TestCase):

    def setUp(self) -> None:
        super().setUp()
        self.plugin = MagicMock()
        self.pdb_file = os.path.join(fixtures_dir, '7c4u.pdb')
        self.map_file = os.path.join(fixtures_dir, 'emd_30288.map.gz')
        self.map_mesh = MapMesh(self.plugin)

    def test_add_map_gz_file(self):
        # Set future result for request_complexes mock
        fut = asyncio.Future()
        fut.set_result([structure.Complex()])
        self.plugin.add_to_workspace.return_value = fut
        # run add_map_gz, and make sure map_manager is created on internal map_manager
        self.assertTrue(isinstance(self.map_mesh.map_manager, type(None)))
        self.map_mesh.add_map_gz_file(self.map_file)
        self.assertTrue(isinstance(self.map_mesh.map_manager, map_manager))

    def test_load(self):
        async def validate_load(self):
            """Validate that running load() generates the NanomeMesh."""
            map_file = os.path.join(fixtures_dir, 'emd_30288.map.gz')
            expected_vertices = 4437
            expected_normals = 4437
            expected_triangles = 7986
            self.map_mesh.add_map_gz_file(map_file)
            isovalue = 0.2
            opacity = 0.65
            radius = 5
            position = 0.1

            fut = asyncio.Future()
            fut.set_result([structure.Complex()])
            self.plugin.add_to_workspace.return_value = fut
            mesh = self.map_mesh.mesh
            self.assertEqual(len(mesh.vertices), 0)
            self.assertEqual(len(mesh.normals), 0)
            self.assertEqual(len(mesh.triangles), 0)
            await self.map_mesh.load(isovalue, opacity, radius, position)
            self.assertEqual(len(mesh.vertices), expected_vertices)
            self.assertEqual(len(mesh.normals), expected_normals)
            self.assertEqual(len(mesh.triangles), expected_triangles)
        run_awaitable(validate_load, self)
