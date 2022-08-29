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

    @property
    def ln_group_btns(self):
        return self._menu.root.find_node('ln_group_btns')

    def render(self, force_enable=False):
        if force_enable:
            self._menu.enabled = True
        groups = self._plugin.groups
        self.render_groups(groups)
        self._plugin.update_menu(self._menu)

    def on_btn_embi_db_pressed(self, btn):
        Logs.message('Loading EMBiDB menu')
        self._plugin.enable_embi_db_menu()
        self.render(force_enable=False)

    def render_groups(self, groups):
        lst = ui.UIList()
        lst.display_rows = 3
        for group_name, filelist in groups.items():
            ln = ui.LayoutNode()
            btn = ln.add_new_button()
            btn.text.value.set_all(group_name)
            Logs.debug(f'Rendering group {group_name}')
            Logs.debug(f'Filelist: {filelist}')
            lst.items.append(ln)
        self.ln_group_btns.set_content(lst)
        self._plugin.update_node(self.ln_group_btns)


class EmbiDBMenu:

    def __init__(self, plugin_instance):
        self._menu = ui.Menu.io.from_json(EMBL_MENU_PATH)
        self._menu.index = 2
        self._plugin = plugin_instance
        self.btn_rcsb_submit.register_pressed_callback(self.on_rcsb_submit)
        self.btn_embl_submit.register_pressed_callback(self.on_embl_submit)

        self.current_group = "Group 1"
        # For development only
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

    def on_rcsb_submit(self, btn):
        pdb_id = self.ti_rcsb_query.input_text
        Logs.debug(f"RCSB query: {pdb_id}")
        pdb_path = self.download_pdb_from_rcsb(pdb_id)
        if not pdb_path:
            return
        self._plugin.add_to_group(pdb_path)

    def on_embl_submit(self, btn):
        query = self.ti_embl_query.input_text
        Logs.debug(f"EMBL query: {query}")
    
    def download_pdb_from_rcsb(self, pdb_id):
        url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
        response = requests.get(url)
        if response.status_code != 200:
            Logs.warning(f"PDB for {pdb_id} not found")
            self._plugin.send_notification(
                nanome.util.enums.NotificationTypes.error,
                f"{pdb_id} not found in RCSB")
            return
        file_path = f'{self.temp_dir}/{pdb_id}.pdb'
        with open(file_path, 'wb') as f:
            f.write(response.content)
        return file_path
    