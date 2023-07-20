import asyncio
import json
import os
import tempfile
import unittest

from nanome.api import structure
from unittest.mock import MagicMock

from plugin.CryoEM import CryoEM
from plugin.models import MapGroup

from distutils.spawn import find_executable

fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')


class CryoEMPluginTestCase(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        super().setUp()
        self.plugin = CryoEM()
        plugin_id = 1
        session_id = 1
        version_table_file = os.path.join(fixtures_dir, "version_table_1_24_2.json")
        with open(version_table_file, 'r') as f:
            version_table = json.load(f)
        self.plugin.set_client(plugin_id, session_id, version_table)
        self.plugin.client = MagicMock()
        # self.plugin.client.reader = MagicMock()
        # self.plugin.client.writer = MagicMock()
        self.map_group = MapGroup(self.plugin)
        self.pdb_file = os.path.join(fixtures_dir, '7c4u.pdb')

        # Make temp copy of mapfile, because a test will delete it.
        self.map_file = os.path.join(fixtures_dir, 'emd_8216.map.gz')

        shapes_mock = asyncio.Future()
        shapes_mock.set_result([MagicMock(), MagicMock()])
        self.plugin.client.shapes_upload_multiple = MagicMock(return_value=shapes_mock)

    def tearDown(self):
        super().tearDown()
        self.plugin.temp_dir.cleanup()

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

    async def test_add_model_to_group(self):
        await self.plugin.menu.render()
        selected_mapgroup_name = self.plugin.menu.get_selected_mapgroup()
        selected_mapgroup = self.plugin.get_group(selected_mapgroup_name)

        add_bonds_fut = asyncio.Future()
        add_bonds_fut.set_result(None)
        self.plugin.client.add_bonds = MagicMock(return_value=add_bonds_fut)

        add_to_workspace_fut = asyncio.Future()
        add_to_workspace_fut.set_result([structure.Complex()])
        self.plugin.client.add_to_workspace = MagicMock(return_value=add_to_workspace_fut)
        self.assertTrue(selected_mapgroup.model_complex is None)
        self.assertTrue(selected_mapgroup is not None)
        await self.plugin.add_model_to_group(self.pdb_file)
        self.assertTrue(isinstance(selected_mapgroup.model_complex, structure.Complex))

        # Make sure if no groups exist when this is called, a new one is created.
        self.plugin.groups = []
        self.assertEqual(len(self.plugin.groups), 0)
        await self.plugin.add_model_to_group(self.pdb_file)
        self.assertEqual(len(self.plugin.groups), 1)

    async def test_add_mapfile_to_group(self):
        await self.plugin.menu.render()
        selected_mapgroup_name = self.plugin.menu.get_selected_mapgroup()
        selected_mapgroup = self.plugin.get_group(selected_mapgroup_name)

        add_to_workspace_fut = asyncio.Future()
        add_to_workspace_fut.set_result([structure.Complex()])
        self.plugin.client.add_to_workspace = MagicMock(return_value=add_to_workspace_fut)

        self.assertTrue(selected_mapgroup.map_complex is None)
        self.assertTrue(selected_mapgroup is not None)

        await self.plugin.add_mapfile_to_group(self.map_file)
        self.assertTrue(isinstance(selected_mapgroup.map_complex, structure.Complex))

        # Make sure if no groups exist when this is called, a new one is created.
        self.plugin.groups = []
        self.assertEqual(len(self.plugin.groups), 0)
        await self.plugin.add_mapfile_to_group(self.map_file)
        self.assertEqual(len(self.plugin.groups), 1)

    async def test_delete_mapgroup(self):
        self.assertEqual(len(self.plugin.groups), 1)
        remove_from_workspace_fut = asyncio.Future()
        remove_from_workspace_fut.set_result([structure.Complex()])
        self.plugin.client.remove_from_workspace = MagicMock(return_value=remove_from_workspace_fut)

        request_complex_list = asyncio.Future()
        request_complex_list.set_result([structure.Complex()])
        self.plugin.client.request_complex_list = MagicMock(return_value=request_complex_list)

        existing_group = self.plugin.groups[0]
        # Copy map file to temp file, because the test will delete it.
        temp_map_file = tempfile.NamedTemporaryFile(suffix='.map.gz')
        with open(self.map_file, 'rb') as f:
            temp_map_file.write(f.read())
        await existing_group.add_mapfile(temp_map_file.name)
        self.assertTrue(os.path.exists(existing_group.mapfile))

        await self.plugin.delete_mapgroup(existing_group)
        self.assertEqual(len(self.plugin.groups), 0)
        # Validate that the map file was deleted
        self.assertFalse(os.path.exists(existing_group.mapfile))

    async def test_create_model_complex(self):
        # Test pdb file
        model_complex = await self.plugin.create_model_complex(self.pdb_file)
        self.assertTrue(isinstance(model_complex, structure.Complex))

        # Test sdf file
        sdf_file = os.path.join(fixtures_dir, 'Structure3D_CID_243.sdf')
        sdf_complex = await self.plugin.create_model_complex(sdf_file)
        self.assertTrue(isinstance(sdf_complex, structure.Complex))

        # Test cif file
        cif_file = os.path.join(fixtures_dir, '1fsv.cif')
        cif_complex = await self.plugin.create_model_complex(cif_file)
        self.assertTrue(isinstance(cif_complex, structure.Complex))
