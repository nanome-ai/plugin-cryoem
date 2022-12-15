import asyncio
import os
import unittest
from nanome.api import structure, PluginInstance
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
        PluginInstance._instance = self.plugin
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

    @patch('nanome._internal._network.PluginNetwork._instance', return_value=asyncio.Future())
    def test_generate_mesh(self, instance_mock):
        # Assert that attributes are set after load_map called.
        async def validate_generate_mesh(self):
            fut = asyncio.Future()
            fut.set_result([structure.Complex()])
            self.plugin.add_to_workspace.return_value = fut

            map_file = os.path.join(fixtures_dir, 'emd_30288.map.gz')
            expected_vertices = 14735
            # Make sure vertices are added to mesh
            self.assertEqual(len(self.map_group.map_mesh.computed_vertices), 0)
            await self.map_group.add_map_gz(map_file)
            await self.map_group.generate_mesh()
            self.assertEqual(len(self.map_group.map_mesh.computed_vertices), expected_vertices)
        run_awaitable(validate_generate_mesh, self)
        # run_awaitable(validate_generate_mesh, self)


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
            expected_vertices = 285798
            expected_normals = 537129
            expected_triangles = 537129
            self.map_mesh.add_map_gz_file(map_file)
            isovalue = 0.2
            opacity = 0.65
            radius = -1
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
