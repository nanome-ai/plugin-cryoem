from os import path
from nanome.api import ui

BASE_PATH = path.dirname(f'{path.realpath(__file__)}')
MAIN_MENU_PATH = path.join(BASE_PATH, 'main_menu.json')


class MainMenu:

    def __init__(self, plugin_instance):
        self._menu = ui.Menu.io.from_json(MAIN_MENU_PATH)
        self._plugin_instance = plugin_instance
    
    def enable(self):
        self._menu.enabled = True
        self._plugin_instance.update_menu(self._menu)
