import asyncio
import math
import os
from nanome_sdk.session import UIManager
import tempfile
import unittest

from nanome.api import structure, ui
from unittest.mock import MagicMock

import plugin
from plugin import models, menu
from plugin.utils import EMDBMetadataParser
import threading

fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')


class EditMeshMenuTestCase(unittest.IsolatedAsyncioTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.plugin = MagicMock()
        self.plugin.temp_dir = tempfile.TemporaryDirectory()
        self.plugin.client = MagicMock()
        self.plugin.ui_manager = UIManager()
        self.pdb_file = os.path.join(fixtures_dir, '7c4u.pdb')
        self.mapgz_file = os.path.join(fixtures_dir, 'emd_8216.map.gz')
        self.map_group = models.MapGroup(self.plugin)
        self.menu = menu.EditMeshMenu(self.map_group, self.plugin)

        fut = asyncio.Future()
        fut.set_result([structure.Complex()])
        self.plugin.client.add_to_workspace.return_value = fut

        shapes_mock = asyncio.Future()
        shapes_mock.set_result([MagicMock(), MagicMock()])
        self.plugin.client.shapes_upload_multiple = MagicMock(return_value=shapes_mock)

    def tearDown(self):
        super().tearDown()
        # We sometimes need to wait for generate_histogram thread to finish
        # before we can cleanup the temporary directory
        for thread in threading.enumerate():
            try:
                thread.join()
            except RuntimeError:
                pass
        self.plugin.temp_dir.cleanup()

    async def test_render_no_map(self):
        self.menu.render(self.map_group)
        self.assertTrue(self.map_group.group_name in self.menu._menu.title)
        self.assertEqual(len(self.menu.lst_files.items), 0)
        self.assertEqual(self.menu.sld_opacity.current_value, self.map_group.opacity)

    async def test_render_with_map(self):
        await self.map_group.add_mapfile(self.mapgz_file)
        await self.map_group.generate_full_mesh()
        self.assertTrue(self.map_group.has_map())
        self.menu.render(self.map_group)
        self.assertEqual(len(self.menu.lst_files.items), 1)

        rel_tol = 1e-6
        sld_isovalue = self.menu.get_isovalue_from_slider()
        self.assertTrue(math.isclose(sld_isovalue, self.map_group.isovalue, rel_tol=rel_tol))

        sld_min_value = self.menu.sld_isovalue.min_value / self.menu.isovalue_scaling_factor
        sld_max_value = self.menu.sld_isovalue.max_value / self.menu.isovalue_scaling_factor
        self.assertTrue(math.isclose(sld_min_value, self.map_group.hist_x_min, rel_tol=rel_tol))
        self.assertTrue(math.isclose(sld_max_value, self.map_group.hist_x_max, rel_tol=rel_tol))

    async def test_generate_histogram(self):
        await self.map_group.add_mapfile(self.mapgz_file)
        await self.map_group.generate_full_mesh()
        self.menu.render(self.map_group)

        # Make sure slider values approximately match map_group values
        rel_tol = 1e-6
        sld_isovalue = self.menu.get_isovalue_from_slider()
        self.assertTrue(math.isclose(sld_isovalue, self.map_group.isovalue, rel_tol=rel_tol))

        sld_min_value = self.menu.sld_isovalue.min_value / self.menu.isovalue_scaling_factor
        sld_max_value = self.menu.sld_isovalue.max_value / self.menu.isovalue_scaling_factor
        self.assertTrue(math.isclose(sld_min_value, self.map_group.hist_x_min, rel_tol=rel_tol))
        self.assertTrue(math.isclose(sld_max_value, self.map_group.hist_x_max, rel_tol=rel_tol))
        self.assertTrue(isinstance(self.menu.ln_img_histogram.get_content(), ui.Image))


class LoadFromEmdbMenuTestCase(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.plugin = plugin.CryoEM.CryoEM()
        self.plugin.client = MagicMock()
        self.menu = menu.LoadFromEmdbMenu(self.plugin)
        self.menu._menu.enabled = False

    def test_render(self):
        self.assertEqual(self.menu._menu.enabled, False)
        self.menu.render()
        self.assertEqual(self.menu._menu.enabled, True)

    def test_on_browse_emdb(self):
        btn = MagicMock()
        open_url_mock = MagicMock()
        self.plugin.client.open_url = open_url_mock
        self.menu.on_browse_emdb(btn)
        open_url_mock.assert_called_once()

    async def test_on_emdb_submit(self):
        self.menu.ti_embl_query.input_text = '8216'

        metadata_file = os.path.join(fixtures_dir, 'metadata_8216.xml')
        map_gz_file = os.path.join(fixtures_dir, 'emd_8216.map.gz')

        with open(metadata_file, 'rb') as f:
            parser = EMDBMetadataParser(f.read())

        metadata_mock = MagicMock(return_value=parser)
        self.menu.download_metadata_from_emdbid = metadata_mock

        fut = asyncio.Future()
        fut.set_result(map_gz_file)
        mapgz_download_mock = MagicMock(return_value=fut)
        self.menu.download_mapgz_from_emdbid = mapgz_download_mock

        btn = MagicMock()
        await self.menu.on_emdb_submit(btn)

        # Make sure mocks were called.
        metadata_mock.assert_called_once()
        mapgz_download_mock.assert_called_once()
