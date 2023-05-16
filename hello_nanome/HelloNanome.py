import logging
from nanome.api.ui import Menu
from nanome.util import enums, Logs

from .session_client import SessionClient

logging.basicConfig(level=logging.DEBUG)
fmt = '%(levelname)s - %(name)s - %(message)s'
logging.root.handlers[0].setFormatter(logging.Formatter(fmt))

logger = logging.getLogger(__name__)


class HelloNanomePlugin:

    def __init__(self, plugin_id, session_id, version_table):
        self.plugin_id = plugin_id
        self.session_id = session_id
        self.version_table = version_table
        self.client = SessionClient(self.plugin_id, self.session_id, self.version_table)
        self.menu = None
        self.label = None

    async def on_start(self):
        self.menu = Menu()
        self.menu.title = 'Hello Nanome'
        self.menu.width = 1
        self.menu.height = 1

        msg = 'Hello Nanome!'
        node = self.menu.root.create_child_node()
        self.label = node.add_new_label(msg)
        Logs.message(msg)

    async def on_run(self):
        # Print the number of complexes in the workspace
        # to the Menu.
        comp_list = await self.client.request_complex_list()
        msg = f'Hello Nanome. There are {len(comp_list)} complexes in the workspace.'
        Logs.message(msg)
        self.client.apply_color_scheme(
            enums.ColorScheme.Rainbow, enums.ColorSchemeTarget.All, False)
        self.label.text_value = msg
        self.menu.enabled = True
        self.client.update_menu(self.menu)
        for comp in comp_list:
            comp.boxed = not comp.boxed
        self.client.update_structures_shallow(comp_list)\

    @property
    def request_futs(self):
        return self.client.request_futs
