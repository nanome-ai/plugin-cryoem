import asyncio
import os
from nanome_sdk.session import UIManager
import tempfile
import unittest

from nanome.api import structure, ui
from unittest.mock import MagicMock

from plugin import models, menu
import threading

fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')


def run_awaitable(awaitable, *args, **kwargs):
    loop = asyncio.get_event_loop()
    if loop.is_running:
        loop = asyncio.new_event_loop()
    result = loop.run_until_complete(awaitable(*args, **kwargs))
    loop.close()
    return result


class EditMeshMenuTestCase(unittest.TestCase):

    def setUp(self) -> None:
        super().setUp()
        self.plugin = MagicMock()
        self.plugin.temp_dir = tempfile.TemporaryDirectory()
        self.plugin.client = MagicMock()
        self.plugin.ui_manager = UIManager()
        self.pdb_file = os.path.join(fixtures_dir, '7c4u.pdb')
        self.map_file = os.path.join(fixtures_dir, 'emd_30288.map.gz')
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

    def test_render_no_map(self):

        async def validate_render_no_map():
            self.menu.render(self.map_group)
            self.assertTrue(self.map_group.group_name in self.menu._menu.title)
            self.assertEqual(len(self.menu.lst_files.items), 0)
            self.assertEqual(self.menu.sld_isovalue.current_value, self.map_group.isovalue)
            self.assertEqual(self.menu.sld_opacity.current_value, self.map_group.opacity)
        run_awaitable(validate_render_no_map)

    def test_render_with_map(self):
        async def validate_render_with_map():
            await self.map_group.add_map_gz(self.map_file)
            await self.map_group.generate_full_mesh()
            self.assertTrue(self.map_group.has_map())
            self.menu.render(self.map_group)
            self.assertEqual(len(self.menu.lst_files.items), 1)
            self.assertEqual(self.menu.sld_isovalue.min_value, self.map_group.hist_x_min)
            self.assertEqual(self.menu.sld_isovalue.max_value, self.map_group.hist_x_max)
        run_awaitable(validate_render_with_map)

    def test_generate_histogram(self):
        async def validate_generate_histogram():
            await self.map_group.add_map_gz(self.map_file)
            await self.map_group.generate_full_mesh()
            original_hist_x_min = self.map_group.hist_x_min
            original_hist_x_max = self.map_group.hist_x_max
            self.menu.render(self.map_group)
            self.assertNotEqual(self.map_group.hist_x_min, original_hist_x_min)
            self.assertNotEqual(self.map_group.hist_x_max, original_hist_x_max)
            self.assertEqual(self.menu.sld_isovalue.min_value, self.map_group.hist_x_min)
            self.assertEqual(self.menu.sld_isovalue.max_value, self.map_group.hist_x_max)
            self.assertTrue(isinstance(self.menu.ln_img_histogram.get_content(), ui.Image))
        run_awaitable(validate_generate_histogram)
