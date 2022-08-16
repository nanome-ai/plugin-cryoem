import asyncio
import os
import unittest

from unittest.mock import MagicMock
from plugin.CryoEM import CryoEM

fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')


def run_awaitable(awaitable, *args, **kwargs):
    loop = asyncio.get_event_loop()
    if loop.is_running:
        loop = asyncio.new_event_loop()
    result = loop.run_until_complete(awaitable(*args, **kwargs))
    loop.close()
    return result


class PluginFunctionTestCase(unittest.TestCase):

    def setUp(self):
        self.plugin_instance = CryoEM()
        # self.plugin_instance.start()
        self.plugin_instance._network = MagicMock()

    def test_plugin(self):
        self.assertTrue(isinstance(self.plugin_instance, CryoEM))
