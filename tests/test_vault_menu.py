import asyncio
import json
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from plugin.vault_menu import VaultMenu
from plugin import CryoEM
from plugin.vault_manager import VaultManager


fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')


class VaultMenuTestCase(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        api_key = 'abc1234'
        server_url = 'https://vault.example.com'
        self.vault_manager = VaultManager(api_key, server_url)
        self.plugin_instance = CryoEM()
        self.plugin_instance.client = MagicMock()
        org = 'test_org'
        account_id = 'user-xxxx'
        self.vault_menu = VaultMenu(self.plugin_instance, self.vault_manager, org, account_id)

        self.root_list_items_mock = json.loads(
            '{"success": true, "locked_path": null, "locked": [], "folders": [{"name": "shared", "size": "", "size_text": "", "created": "", "created_text": ""}], "files": []}')
        self.shared_list_items_mock = json.loads(
            '{"success": true, "locked_path": null, "locked": [], "folders": [], "files": [{"name": "emd_8216.map.gz", "size": 1227499, "size_text": "1.2MB", "created": "2023-06-30 15:59", "created_text": "10 days ago"}]}')

    def test_show_menu(self):
        self.vault_manager.list_path = MagicMock(return_value=self.root_list_items_mock)
        self.vault_menu.menu.enabled = False
        self.vault_menu.show_menu()
        self.assertTrue(self.vault_menu.menu.enabled)

    async def test_load_file(self):
        filename = 'emd_8216.map.gz'
        mock_file = os.path.join(fixtures_dir, filename)

        add_mapfile_fut = asyncio.Future()
        add_mapfile_fut.set_result(MagicMock())
        self.plugin_instance.add_mapfile_to_group = MagicMock(return_value=add_mapfile_fut)

        head_response_mock = MagicMock()
        head_response_mock.headers = {'Content-Length': os.path.getsize(mock_file)}

        get_response_mock = MagicMock()
        with open(mock_file, 'rb') as f:
            read_fut = asyncio.Future()
            read_mock = MagicMock()

            first_read = asyncio.Future()
            first_read.set_result(f.read())
            second_read = asyncio.Future()
            second_read.set_result(None)

            read_mock.side_effect = [first_read, second_read]
            read_fut.set_result(read_mock)
            get_response_mock.content.read = read_mock

        mock_head = patch('aiohttp.ClientSession.head', new_callable=AsyncMock, return_value=head_response_mock)
        mock_get = patch('aiohttp.ClientSession.get', new_callable=AsyncMock, return_value=get_response_mock)
        with mock_head as mock_head, mock_get as mock_get:
            await self.vault_menu.load_file(filename)
        self.plugin_instance.add_mapfile_to_group.assert_called_once()
        mock_head.assert_called_once()
        mock_get.assert_called_once()
