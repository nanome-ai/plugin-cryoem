import functools
import os
import nanome
import requests
from os import path
from nanome.api import ui
from nanome.util import Logs, async_callback, enums

from .models import MapGroup

MENU_JSON_PATH = path.join(path.dirname(f'{path.realpath(__file__)}'), 'menu_json')
MAIN_MENU_PATH = path.join(MENU_JSON_PATH, 'main_menu.json')
EMBL_MENU_PATH = path.join(MENU_JSON_PATH, 'embl_search_menu.json')
GROUP_DETAIL_MENU_PATH = path.join(MENU_JSON_PATH, 'group_details.json')
MAP_FILETYPES = ['.map', '.map.gz']

__all__ = ['MainMenu', 'EMBLMenu', 'EditMeshMenu']


class MainMenu:

    def __init__(self, plugin_instance):
        self._menu = ui.Menu.io.from_json(MAIN_MENU_PATH)
        self._plugin = plugin_instance
        self.btn_search_menu.register_pressed_callback(self.on_btn_search_menu_pressed)

    @property
    def btn_search_menu(self):
        return self._menu.root.find_node('btn_embi_db').get_content()

    @property
    def ln_group_btns(self):
        return self._menu.root.find_node('ln_group_btns')

    def render(self, complexes, force_enable=False):
        if force_enable:
            self._menu.enabled = True

        for comp in complexes:
            pass

        groups = self._plugin.groups
        self.render_map_groups(groups)
        self._plugin.update_menu(self._menu)

    def on_btn_search_menu_pressed(self, btn):
        Logs.message('Loading Search menu')
        self._plugin.enable_search_menu()

    def render_map_groups(self, groups):
        lst = ui.UIList()
        lst.display_rows = 3
        for map_group in groups.values():
            group_name = map_group.group_name
            ln = ui.LayoutNode()
            btn = ln.add_new_button()
            btn.text.value.set_all(group_name)
            btn.register_pressed_callback(
                functools.partial(self.open_group_details, map_group))
            lst.items.append(ln)
        self.ln_group_btns.set_content(lst)
        self._plugin.update_node(self.ln_group_btns)

    def open_group_details(self, map_group, btn):
        Logs.message('Loading group details menu')
        group_menu = EditMeshMenu(map_group, self._plugin)
        group_menu.render(map_group)


class SearchMenu:

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

    @async_callback
    async def on_rcsb_submit(self, btn):
        pdb_id = self.ti_rcsb_query.input_text
        Logs.debug(f"RCSB query: {pdb_id}")
        pdb_path = self.download_pdb_from_rcsb(pdb_id)
        if not pdb_path:
            return
        await self._plugin.add_to_group(pdb_path)

    @async_callback
    async def on_embl_submit(self, btn):
        embid_id = self.ti_embl_query.input_text
        Logs.debug(f"EMBL query: {embid_id}")
        map_file = self.download_cryoem_map_from_emdbid(embid_id)
        await self._plugin.add_to_group(map_file)

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

    def download_cryoem_map_from_emdbid(self, emdbid):
        Logs.message("Downloading EM data for EMDBID:", emdbid)
        url = f"https://ftp.ebi.ac.uk/pub/databases/emdb/structures/EMD-{emdbid}/map/emd_{emdbid}.map.gz"
        # Write the map to a .map file
        file_path = f'{self.temp_dir}/{emdbid}.map.gz'
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(file_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            # self._plugin.map_file = map_tempfile
            # self._plugin.load_map()
            # self._plugin.generate_histogram()
            # ws = await self._plugin.request_workspace()
            # await self._plugin.set_current_complex_generate_surface(ws)
        return file_path


class EditMeshMenu:

    def __init__(self, map_group, plugin_instance):
        self.map_group = map_group
        self._menu = ui.Menu.io.from_json(GROUP_DETAIL_MENU_PATH)
        self._plugin = plugin_instance
        self._menu.index = 20
        self.sld_isovalue.register_changed_callback(self.update_isovalue_lbl)
        self.sld_isovalue.register_released_callback(self.redraw_map)
        self.sld_opacity.register_changed_callback(self.update_opacity_lbl)
        self.sld_opacity.register_released_callback(self.update_color)
        self.sld_size.register_changed_callback(self.update_size_lbl)
        self.sld_size.register_released_callback(self.redraw_map)
        self.set_isovalue_ui(map_group.isovalue)
        self.set_opacity_ui(map_group.opacity)
        self.set_size_ui(map_group.limited_view_range)
        self.btn_show_hide_map.switch.active = True
        self.btn_show_hide_map.toggle_on_press = True
        self.btn_show_hide_map.register_pressed_callback(self.toggle_map_visibility)
        self.btn_wireframe.switch.active = True
        self.btn_wireframe.toggle_on_press = True
        self.btn_wireframe.register_pressed_callback(self.set_wireframe_mode)

    def set_isovalue_ui(self, isovalue):
        self.sld_isovalue.current_value = isovalue
        self.lbl_isovalue.text_value = str(round(isovalue, 2))

    def set_opacity_ui(self, opacity: float):
        self.sld_opacity.current_value = opacity
        self.lbl_opacity_value.text_value = str(round(opacity, 2))
    
    def set_size_ui(self, size: float):
        self.sld_size.current_value = size
        self.lbl_size_value.text_value = str(round(size, 2))

    @property
    def sld_isovalue(self):
        return self._menu.root.find_node('sld_isovalue').get_content()

    @property
    def sld_opacity(self):
        return self._menu.root.find_node('sld_opacity').get_content()

    @property
    def lbl_opacity_value(self):
        return self._menu.root.find_node('lbl_opacity_value').get_content()

    @property
    def lbl_isovalue(self):
        return self._menu.root.find_node('lbl_isovalue').get_content()

    @property
    def btn_show_hide_map(self):
        return self._menu.root.find_node('btn_show_hide_map').get_content()

    @property
    def btn_wireframe(self):
        return self._menu.root.find_node('btn_wireframe').get_content()

    def update_isovalue_lbl(self, sld):
        self.lbl_isovalue.text_value = str(round(sld.current_value, 2))
        self._plugin.update_content(self.lbl_isovalue, sld)

    def update_opacity_lbl(self, sld):
        self.lbl_opacity_value.text_value = str(round(sld.current_value, 2))
        self._plugin.update_content(self.lbl_opacity_value, sld)

    def update_size_lbl(self, sld):
        self.lbl_size_value.text_value = str(round(sld.current_value, 2))
        self._plugin.update_content(self.lbl_size_value, sld)

    @async_callback
    async def update_color(self, *args):
        color_scheme = self.color_scheme
        opacity = self.opacity
        await self.map_group.update_color(color_scheme, opacity)
        if self.map_group.mesh:
            self.map_group.mesh.upload()

    @async_callback
    async def redraw_map(self, content):
        self.map_group.isovalue = self.isovalue
        self.map_group.opacity = self.opacity
        self.map_group.color_scheme = self.color_scheme
        self.map_group.limited_view_range = self.size
        if self.map_group.mesh:
            await self._plugin.render_mesh(self.map_group)

    @property
    def img_histogram(self):
        return self._menu.root.find_node('img_histogram').get_content()

    @property
    def dd_color_scheme(self):
        return self._menu.root.find_node('dd_color_scheme').get_content()

    @property
    def temp_dir(self):
        return self._plugin.temp_dir.name

    def render(self, map_group: MapGroup):
        self._menu.title = f'{map_group.group_name} Map'
        # Populate file list
        lst = ui.UIList()
        lst.display_rows = 3
        for filepath in map_group.files:
            ln = ui.LayoutNode()
            btn = ln.add_new_button()
            filename = os.path.basename(filepath)
            btn.text.value.set_all(filename)
            lst.items.append(ln)
        # Generate histogram
        if len(map_group.files) > 1:
            img_filepath = map_group.generate_histogram(self.temp_dir)
            self.img_histogram.file_path = img_filepath

        self.sld_isovalue.current_value = self.map_group.isovalue
        self.sld_opacity.current_value = self.map_group.opacity
        self.sld_size.current_value = self.map_group.limited_view_range

        self.dd_color_scheme.items = [
            nanome.ui.DropdownItem(name)
            for name in ["Bfactor", "Element", "Chain"]
        ]
        self.dd_color_scheme.register_item_clicked_callback(self.update_color)
        self.dd_color_scheme.items[0].selected = True
        self._plugin.update_menu(self._menu)

    @property
    def sld_size(self):
        return self._menu.root.find_node('sld_size').get_content()

    @property
    def lbl_size_value(self):
        return self._menu.root.find_node('lbl_size_value').get_content()

    @property
    def isovalue(self):
        return self.sld_isovalue.current_value

    @property
    def opacity(self):
        return self.sld_opacity.current_value

    @property
    def size(self):
        return self.sld_size.current_value

    @property
    def color_scheme(self):
        item = next(item for item in self.dd_color_scheme.items if item.selected)
        if item.name == "Element":
            color_scheme = enums.ColorScheme.Element
        elif item.name == "Bfactor":
            color_scheme = enums.ColorScheme.BFactor
        elif item.name == "Chain":
            color_scheme = enums.ColorScheme.Chain
        return color_scheme

    def set_wireframe_mode(self, btn):
        toggle = btn.selected
        Logs.message(f"Wireframe mode set to {toggle}")
        self.map_group.toggle_wireframe_mode(toggle)
        self.map_group.mesh.upload()

    @async_callback
    async def toggle_map_visibility(self, btn):
        toggle = btn.selected
        Logs.message(f"Map visibility set to {toggle}")
        opacity = self.opacity if toggle else 0
        color = self.map_group.color_scheme
        await self.map_group.update_color(color, opacity)
        self.map_group.mesh.upload()
