from .session_client import SessionClient
from .ui_manager import UIManager
import logging
from .utils import run_function_or_coroutine

logging.basicConfig(level=logging.DEBUG)


class NanomePlugin:
    """Used as parent class for all Nanome plugins.
    Provides attributes to class instances that inherit from it.

    self.client: SessionClient for sending/receiving messages to/from Nanome
    self.ui_manager: UIManager for creating and managing UI elements and callbacks
    """
    client = None
    ui_manager = UIManager()

    def __init__(self):
        self.handlers = {}

    def set_client(self, plugin_id, session_id, version_table):
        """Used internally by the PluginServer."""
        self.client = SessionClient(plugin_id, session_id, version_table)

    def on_start(self, func=None):
        # If func provided, save as on_start handler
        if func is not None:
            self.handlers['on_start'] = func

    def on_stop(self):
        pass

    async def on_complex_added_removed(self):
        pass

    def on_run(self, func=None):
        if func is not None:
            self.handlers['on_run'] = func

    @property
    def request_futs(self):
        return getattr(self.client, 'request_futs', None)

    def _run_handler(self, handler_name):
        handler = self.handlers.get(handler_name)
        if handler:
            task = run_function_or_coroutine(handler)
            return task
