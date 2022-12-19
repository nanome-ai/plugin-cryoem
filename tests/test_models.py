import asyncio
import os
import nanome
import tempfile
import unittest

from nanome.api import structure, PluginInstance, shapes
from unittest.mock import MagicMock, patch
from iotbx.map_manager import map_manager

from mmtbx.model.model import manager
from plugin import models
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
        nanome._internal._network.PluginNetwork._instance = MagicMock()
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

    def test_generate_histogram(self):
        # Assert that attributes are set after load_map called.
        async def validate_generate_histogram(self):
            fut = asyncio.Future()
            fut.set_result([structure.Complex()])
            self.plugin.add_to_workspace.return_value = fut

            map_file = os.path.join(fixtures_dir, 'emd_30288.map.gz')
            await self.map_group.add_map_gz(map_file)
            await self.map_group.generate_mesh()
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

        fut = asyncio.Future()
        fut.set_result([structure.Complex()])
        self.plugin.add_to_workspace.return_value = fut

    def test_add_map_gz_file(self):
        # Set future result for request_complexes mock
        fut = asyncio.Future()
        fut.set_result([structure.Complex()])
        self.plugin.add_to_workspace.return_value = fut
        # run add_map_gz, and make sure map_manager is created on internal map_manager
        self.assertTrue(isinstance(self.map_mesh.map_manager, type(None)))
        self.map_mesh.add_map_gz_file(self.map_file)
        self.assertTrue(isinstance(self.map_mesh.map_manager, map_manager))

    def test_load_no_limit_view(self):
        """Validate that running load() generates the NanomeMesh.

        when radius is set to -1, the mesh should be generated for the entire map.
        """
        async def validate_load(self):
            map_file = os.path.join(fixtures_dir, 'emd_30288.map.gz')
            expected_vertices = 285798
            expected_normals = 537129
            expected_triangles = 537129
            self.map_mesh.add_map_gz_file(map_file)
            isovalue = 0.2
            opacity = 0.65
            radius = -1  # Indicates no limit view
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

    def test_load_limit_view(self):
        """Validate that running load() generates the NanomeMesh.

        when radius is set >= 0, only partial mesh should be generated.
        """
        async def validate_load_limit_view(self):
            map_file = os.path.join(fixtures_dir, 'emd_30288.map.gz')
            expected_vertices = 4440
            expected_normals = 4440
            expected_triangles = 8034
            self.map_mesh.add_map_gz_file(map_file)
            isovalue = 0.2
            opacity = 0.65
            radius = 5  # Indicates limit view to 15 angstroms around position
            position = [0, 0, 0]

            mesh = self.map_mesh.mesh
            self.assertEqual(len(mesh.vertices), 0)
            self.assertEqual(len(mesh.normals), 0)
            self.assertEqual(len(mesh.triangles), 0)
            await self.map_mesh.load(isovalue, opacity, radius, position)
            self.assertEqual(len(mesh.vertices), expected_vertices)
            self.assertEqual(len(mesh.normals), expected_normals)
            self.assertEqual(len(mesh.triangles), expected_triangles)
        run_awaitable(validate_load_limit_view, self)


class ViewportEditorTestCase(unittest.TestCase):

    def setUp(self) -> None:
        super().setUp()
        self.plugin = MagicMock()
        nanome.PluginInstance._instance = MagicMock()
        nanome._internal._network.PluginNetwork._instance = MagicMock()
        self.pdb_file = os.path.join(fixtures_dir, '7c4u.pdb')
        self.map_file = os.path.join(fixtures_dir, 'emd_30288.map.gz')
        self.map_group = models.MapGroup(self.plugin)
        self.viewport_editor = models.ViewportEditor(self.plugin, self.map_group)

        # Mock add_to_workspace call
        fut = asyncio.Future()
        fut.set_result([structure.Complex()])
        self.plugin.add_to_workspace.return_value = fut

    def test_enable(self):
        async def validate_enable(self):
            await self.map_group.add_map_gz(self.map_file)
            self.assertTrue(self.viewport_editor.complex is None)
            self.assertTrue(self.viewport_editor.sphere is None)
            await self.viewport_editor.enable()
            self.assertTrue(isinstance(self.viewport_editor.complex, structure.Complex))
            self.assertTrue(isinstance(self.viewport_editor.sphere, shapes.Sphere))
        run_awaitable(validate_enable, self)

    def test_disable(self):
        async def validate_disable(self):
            await self.map_group.add_map_gz(self.map_file)
            await self.viewport_editor.enable()
            self.assertTrue(isinstance(self.viewport_editor.complex, structure.Complex))
            self.assertTrue(isinstance(self.viewport_editor.sphere, shapes.Sphere))
            self.viewport_editor.disable()
            self.assertTrue(self.viewport_editor.complex is None)
            self.assertTrue(self.viewport_editor.sphere is None)
        run_awaitable(validate_disable, self)

    def test_apply(self):
        async def validate_apply(self):
            await self.map_group.add_map_gz(self.map_file)
            await self.map_group.generate_mesh()
            initial_vertices = self.map_group.map_mesh.computed_vertices
            self.assertTrue(len(initial_vertices) > 0)
            await self.viewport_editor.enable()
            # Set up request_complexes mock
            request_complexes_fut = asyncio.Future()
            request_complexes_fut.set_result([self.viewport_editor.complex])
            self.plugin.request_complexes.return_value = request_complexes_fut
            await self.viewport_editor.apply()
            new_vertices = self.map_group.map_mesh.computed_vertices
            self.assertTrue(len(new_vertices) < len(initial_vertices))
        run_awaitable(validate_apply, self)
