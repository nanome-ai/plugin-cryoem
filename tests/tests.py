import asyncio
import os
import unittest
from unittest.mock import MagicMock, patch

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
        self.map_group.add_map_gz(self.map_file)
        self.assertTrue(isinstance(self.map_group.map_mesh, MapMesh))

    def test_generate_mesh(self):
        # Assert that attributes are set after load_map called.
        run_awaitable(self.validate_generate_mesh)

    @patch('nanome._internal._network._PluginNetwork._instance')
    @patch('nanome.api.plugin_instance.PluginInstance.create_writing_stream')
    @patch('nanome.api.plugin_instance.PluginInstance.request_workspace')
    async def validate_generate_mesh(self):
        breakpoint()
        await self.map_group.add_map_gz(self.map_file)
        self.assertEqual(len(self.map_group.map_mesh.vertices), 0)
        await self.map_group.generate_mesh()
        self.assertTrue(len(self.map_group.map_mesh.computed_vertices) > 0)

    # def test_toggle_wireframe_mode(self):
    #     # wireframe_mode = self.map_group.wireframe_mode
    #     self.assertEqual(self.map_group.wireframe_mode, False)
    #     self.map_group.toggle_wireframe_mode(True)
    #     self.assertEqual(self.map_group.wireframe_mode, True)
    #     self.map_group.toggle_wireframe_mode(False)
    #     self.assertEqual(self.map_group.wireframe_mode, False)
