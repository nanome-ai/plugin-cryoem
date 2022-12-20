import asyncio
import os
import nanome
import unittest

from nanome.api import structure, PluginInstance
from unittest.mock import MagicMock

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


class CryoEMPluginTestCase(unittest.TestCase):

    def setUp(self):
        super().setUp()
        PluginInstance._instance = MagicMock()
        nanome._internal._network.PluginNetwork._instance = MagicMock()
        self.plugin = CryoEM()
        # Mock args that are passed to setup plugin instance networking
        session_id = plugin_network = pm_queue_in = pm_queue_out = custom_data = \
            log_pipe_conn = original_version_table = permissions = MagicMock()
        self.plugin._setup(
            session_id, plugin_network, pm_queue_in, pm_queue_out, log_pipe_conn,
            original_version_table, custom_data, permissions
        )
        self.plugin.start()
        self.map_group = MapGroup(self.plugin)
        self.pdb_file = os.path.join(fixtures_dir, '7c4u.pdb')
        self.map_file = os.path.join(fixtures_dir, 'emd_30288.map.gz')

    def tearDown(self):
        super().tearDown()
        self.plugin.on_stop()

    def test_add_mapgroup(self):
        self.assertEqual(len(self.plugin.groups), 1)
        self.plugin.add_mapgroup()
        self.assertEqual(len(self.plugin.groups), 2)

    def test_get_group(self):
        existing_group = self.plugin.groups[0]
        existing_group_name = existing_group.group_name
        mapgroup = self.plugin.get_group(existing_group_name)
        self.assertEqual(existing_group, mapgroup)
        # Check non existent group returns None
        fake_name = "xyz group"
        mapgroup = self.plugin.get_group(fake_name)
        self.assertTrue(mapgroup is None)

    def test_add_pdb_to_group(self):
        async def validate_add_pdb_to_group():
            self.plugin.menu.render()
            selected_mapgroup_name = self.plugin.menu.get_selected_mapgroup()
            selected_mapgroup = self.plugin.get_group(selected_mapgroup_name)

            add_bonds_fut = asyncio.Future()
            add_bonds_fut.set_result(None)
            self.plugin.add_bonds = MagicMock(return_value=add_bonds_fut)

            add_to_workspace_fut = asyncio.Future()
            add_to_workspace_fut.set_result([structure.Complex()])
            self.plugin.add_to_workspace = MagicMock(return_value=add_to_workspace_fut)
            self.assertTrue(selected_mapgroup.model_complex is None)
            self.assertTrue(selected_mapgroup is not None)
            await self.plugin.add_pdb_to_group(self.pdb_file)
            self.assertTrue(isinstance(selected_mapgroup.model_complex, structure.Complex))

            # Make sure if no groups exist when this is called, a new one is created.
            self.plugin.groups = []
            self.assertEqual(len(self.plugin.groups), 0)
            await self.plugin.add_pdb_to_group(self.pdb_file)
            self.assertEqual(len(self.plugin.groups), 1)
        run_awaitable(validate_add_pdb_to_group)

    def test_add_mapgz_to_group(self):
        async def validate_add_mapgz_to_group():
            self.plugin.menu.render()
            selected_mapgroup_name = self.plugin.menu.get_selected_mapgroup()
            selected_mapgroup = self.plugin.get_group(selected_mapgroup_name)

            add_to_workspace_fut = asyncio.Future()
            add_to_workspace_fut.set_result([structure.Complex()])
            self.plugin.add_to_workspace = MagicMock(return_value=add_to_workspace_fut)

            self.assertTrue(selected_mapgroup.map_complex is None)
            self.assertTrue(selected_mapgroup is not None)

            await self.plugin.add_mapgz_to_group(self.map_file)
            self.assertTrue(isinstance(selected_mapgroup.map_complex, structure.Complex))

            # Make sure if no groups exist when this is called, a new one is created.
            self.plugin.groups = []
            self.assertEqual(len(self.plugin.groups), 0)
            await self.plugin.add_mapgz_to_group(self.map_file)
            self.assertEqual(len(self.plugin.groups), 1)
        run_awaitable(validate_add_mapgz_to_group)

    def test_delete_mapgroup(self):
        async def validate_delete_mapgroup():
            self.assertEqual(len(self.plugin.groups), 1)

            remove_from_workspace_fut = asyncio.Future()
            remove_from_workspace_fut.set_result([structure.Complex()])
            self.plugin.remove_from_workspace = MagicMock(return_value=remove_from_workspace_fut)

            existing_group = self.plugin.groups[0]
            await self.plugin.delete_mapgroup(existing_group)
            self.assertEqual(len(self.plugin.groups), 0)
        run_awaitable(validate_delete_mapgroup)
