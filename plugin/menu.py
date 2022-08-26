from os import path
from nanome.api import ui
from nanome.util import Logs

BASE_PATH = path.dirname(f'{path.realpath(__file__)}')
MAIN_MENU_PATH = path.join(BASE_PATH, 'main_menu.json')
EMBL_MENU_PATH = path.join(BASE_PATH, 'embl_search_menu.json')
MAP_FILETYPES = ['.map', '.map.gz']


class MainMenu:

    def __init__(self, plugin_instance):
        self._menu = ui.Menu.io.from_json(MAIN_MENU_PATH)
        self._plugin = plugin_instance
        self.btn_embi_db.register_pressed_callback(self.on_btn_embi_db_pressed)
    
    @property
    def btn_embi_db(self):
        return self._menu.root.find_node('btn_embi_db').get_content()

    def render(self, force_enable=False):
        if force_enable:
            self._menu.enabled = True
        self._plugin.update_menu(self._menu)

    def on_btn_embi_db_pressed(self, btn):
        Logs.message('Loading EMBiDB menu')
        self._plugin.enable_embi_db_menu()
        self.render(force_enable=False)


class EmbiDBMenu:

    def __init__(self, plugin_instance):
        self._menu = ui.Menu.io.from_json(EMBL_MENU_PATH)
        self._menu.index = 2
        self._plugin = plugin_instance
        self.btn_rcsb_submit.register_pressed_callback(self.query_rcsb)
        self.btn_embl_submit.register_pressed_callback(self.query_embl)
    
    @property
    def btn_rcsb_submit(self):
        return self._menu.root.find_node('btn_rcsb_submit').get_content()
    
    @property
    def btn_embl_submit(self):
        return self._menu.root.find_node('btn_embl_submit').get_content()

    def render(self, force_enable=False):
        if force_enable:
            self._menu.enabled = True
        self._plugin.update_menu(self._menu)

    def query_rcsb(self, btn):
        Logs.message("querying RCSB")
    
    def query_embl(self, btn):
        Logs.message("querying EMBL")