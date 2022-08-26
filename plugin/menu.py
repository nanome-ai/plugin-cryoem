import nanome
import requests
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
        self.ti_rcsb_query.input_text = '7q1u'
        self.ti_embl_query.input_text = '13764'

    @property
    def temp_dir(self):
        return self._plugin.temp_dir.name

    @property
    def btn_rcsb_submit(self):
        return self._menu.root.find_node('btn_rcsb_submit').get_content()
    
    @property
    def btn_embl_submit(self):
        return self._menu.root.find_node('btn_embl_submit').get_content()

    @property
    def ti_rcsb_query(self):
        return self._menu.root.find_node('ti_rcsb_query').get_content()
    
    @property
    def ti_embl_query(self):
        return self._menu.root.find_node('ti_embl_query').get_content()

    def render(self, force_enable=False):
        if force_enable:
            self._menu.enabled = True
        self._plugin.update_menu(self._menu)

    def query_rcsb(self, btn):
        query = self.ti_rcsb_query.input_text
        Logs.debug(f"RCSB query: {query}")
        pdb_path = self.download_pdb_from_rcsb(query)
        # comp = structure.Complex.io.from_pdb(path=pdb_path)
        self._plugin.send_files_to_load([pdb_path])

    def query_embl(self, btn):
        query = self.ti_embl_query.input_text
        Logs.debug(f"EMBL query: {query}")
    
    def download_pdb_from_rcsb(self, pdb_id):
        url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
        response = requests.get(url)
        if response.status_code != 200:
            Logs.warning(f"PDB for {pdb_id} not found")
            self._plugin.send_notification(
                nanome.util.enums.NotificationTypes.error,
                "No PDB found for " + str(self.pdbid),
            )
            return
        file_path = f'{self.temp_dir}{pdb_id}.pdb'
        with open(file_path, 'wb') as f:
            f.write(response.content)
        return file_path
        