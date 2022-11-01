import os
import nanome
import requests
import xml.etree.ElementTree as ET
from functools import partial
from os import path
from nanome.api import ui
from nanome.util import async_callback, enums, Logs
from .models import MapGroup, ViewportEditor


ASSETS_PATH = path.join(path.dirname(f'{path.realpath(__file__)}'), 'assets')
MAIN_MENU_PATH = path.join(ASSETS_PATH, 'main_menu.json')
EMBL_MENU_PATH = path.join(ASSETS_PATH, 'embl_search_menu.json')
GROUP_DETAIL_MENU_PATH = path.join(ASSETS_PATH, 'group_details.json')
GROUP_ITEM_PATH = path.join(ASSETS_PATH, 'group_item.json')

DELETE_ICON = path.join(ASSETS_PATH, 'delete.png')
VISIBLE_ICON = path.join(ASSETS_PATH, 'visible.png')
INVISIBLE_ICON = path.join(ASSETS_PATH, 'invisible.png')
MAP_FILETYPES = ['.map', '.map.gz']

__all__ = ['MainMenu', 'SearchMenu', 'EditMeshMenu']


class MainMenu:

    def __init__(self, plugin_instance: nanome.PluginInstance):
        self._menu = ui.Menu.io.from_json(MAIN_MENU_PATH)
        self._plugin = plugin_instance

        self.pfb_group_item: ui.LayoutNode = ui.LayoutNode.io.from_json(GROUP_ITEM_PATH)
        self.pfb_group_item.find_node('Button Delete').get_content().icon.value.set_all(DELETE_ICON)

        root: ui.LayoutNode = self._menu.root
        self.btn_search_menu: ui.Button = root.find_node('btn_embi_db').get_content()
        self.btn_search_menu.register_pressed_callback(self.on_btn_search_menu_pressed)
        self.lst_groups: ui.UIList = root.find_node('lst_groups').get_content()
        self.btn_add_group: ui.LayoutNode = root.find_node('ln_btn_add_group').get_content()
        self.btn_add_group.register_pressed_callback(self.add_mapgroup)

    def render(self, force_enable=False, selected_mapgroup=None):
        if force_enable:
            self._menu.enabled = True

        groups = self._plugin.groups
        self.render_map_groups(groups, selected_mapgroup)
        self._plugin.update_menu(self._menu)

    def add_mapgroup(self, btn):
        Logs.message('Adding new map group')
        self._plugin.add_mapgroup()

    def on_btn_search_menu_pressed(self, btn):
        Logs.message('Loading Search menu')
        self._plugin.enable_search_menu()

    def render_map_groups(self, groups, selected_mapgroup=None):
        self.lst_groups.items.clear()
        for map_group in groups.values():
            ln: ui.LayoutNode = self.pfb_group_item.clone()
            lbl: ui.Label = ln.find_node('Label').get_content()

            btn_add_to_map: ui.Button = ln.find_node('ln_btn_add_to_map').get_content()
            btn_add_to_map.toggle_on_press = True
            btn_add_to_map.register_pressed_callback(self.select_mapgroup)
            btn_add_to_map.selected = map_group == selected_mapgroup
            lbl.text_value = map_group.group_name

            btn: ui.Button = ln.get_content()
            btn.register_pressed_callback(partial(self.open_group_details, map_group))

            btn_delete: ui.Button = ln.find_node('Button Delete').get_content()
            btn_delete.register_pressed_callback(partial(self.delete_group, map_group))

            btn_toggle: ui.Button = ln.find_node('Button Toggle').get_content()
            btn_toggle.icon.value.set_all(
                VISIBLE_ICON if map_group.visible else INVISIBLE_ICON)
            btn_toggle.register_pressed_callback(partial(self.toggle_group, map_group))

            self.lst_groups.items.append(ln)
        self._plugin.update_content(self.lst_groups)

    def select_mapgroup(self, selected_btn: ui.Button):
        Logs.message('Selecting map group')
        for item in self.lst_groups.items:
            btn: ui.Button = item.find_node('ln_btn_add_to_map').get_content()
            btn.selected = btn._content_id == selected_btn._content_id
        self._plugin.update_content(self.lst_groups)

    def open_group_details(self, map_group, btn=None):
        Logs.message('Loading group details menu')
        group_menu = EditMeshMenu(map_group, self._plugin)
        group_menu.render(map_group)

    @async_callback
    async def delete_group(self, map_group, btn):
        Logs.message(f'Deleting group {map_group.group_name}')
        await self._plugin.delete_mapgroup(map_group)

    def toggle_group(self, map_group, btn: ui.Button):
        Logs.message('Toggling group')
        map_group.visible = not map_group.visible
        btn.icon.value.set_all(
            VISIBLE_ICON if map_group.visible else INVISIBLE_ICON)
        self._plugin.update_content(btn)
        self._plugin.update_structures_shallow([map_group.map_mesh.complex, map_group.model_complex])


class SearchMenu:

    def __init__(self, plugin_instance: nanome.PluginInstance):
        self._menu = ui.Menu.io.from_json(EMBL_MENU_PATH)
        self._menu.index = 2
        self._plugin = plugin_instance

        root: ui.LayoutNode = self._menu.root
        self.btn_rcsb_submit: ui.Button = root.find_node('btn_rcsb_submit').get_content()
        self.btn_embl_submit: ui.Button = root.find_node('btn_embl_submit').get_content()
        self.ti_rcsb_query: ui.TextInput = root.find_node('ti_rcsb_query').get_content()
        self.ti_embl_query: ui.TextInput = root.find_node('ti_embl_query').get_content()

        self.btn_rcsb_submit.register_pressed_callback(self.on_rcsb_submit)
        self.btn_embl_submit.register_pressed_callback(self.on_embl_submit)

        self.current_group = "Group 1"
        # For development only
        # self.ti_rcsb_query.input_text = '7q1u'
        # self.ti_embl_query.input_text = '13764'
        # self.ti_rcsb_query.input_text = '5k7n'
        # self.ti_embl_query.input_text = '8216'
        self.ti_rcsb_query.input_text = '7c4u'
        self.ti_embl_query.input_text = '30288'

    @property
    def temp_dir(self):
        return self._plugin.temp_dir.name

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
        await self._plugin.add_pdb_to_group(pdb_path)

    @async_callback
    async def on_embl_submit(self, btn):
        embid_id = self.ti_embl_query.input_text
        Logs.debug(f"EMBL query: {embid_id}")
        map_file = self.download_cryoem_map_from_emdbid(embid_id)
        isovalue = self.get_preferred_isovalue(embid_id)
        await self._plugin.create_mapgroup_for_file(map_file, isovalue)

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

    def get_preferred_isovalue(self, emdbid):
        # Get the isovalue that is closest to the mean of the map data
        # This is a hack to get a good isovalue for the map
        Logs.message("Downloading EM metadata for EMDBID:", emdbid)
        url = f"https://ftp.ebi.ac.uk/pub/databases/emdb/structures/EMD-{emdbid}/header/emd-{emdbid}.xml"
        response = requests.get(url)
        # Parse xml and get resolution value
        xml_root = ET.fromstring(response.content)
        contour_list_ele = next(xml_root.iter("contour_list"))
        for child in contour_list_ele:
            if child.tag == "contour" and child.attrib["primary"].lower() == 'true':
                level_ele = next(child.iter("level"))
                isovalue = level_ele.text
                break
        try:
            isovalue = float(isovalue)
        except ValueError:
            Logs.warning("Could not parse resolution value from XML")
            isovalue = None
        return isovalue

    def download_cryoem_map_from_emdbid(self, emdbid):
        Logs.message("Downloading EM data for EMDBID:", emdbid)
        # return 'tests/fixtures/emd_30288.map.gz'  # Use this when emdb starts timing out.
        url = f"https://ftp.ebi.ac.uk/pub/databases/emdb/structures/EMD-{emdbid}/map/emd_{emdbid}.map.gz"
        # Write the map to a .map file
        file_path = f'{self.temp_dir}/{emdbid}.map.gz'
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(file_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return file_path


class EditMeshMenu:

    def __init__(self, map_group, plugin_instance: nanome.PluginInstance):
        self.map_group = map_group
        self.viewport_editor = ViewportEditor(map_group, plugin_instance)

        self._menu = ui.Menu.io.from_json(GROUP_DETAIL_MENU_PATH)
        self._plugin = plugin_instance
        self._menu.index = 20

        root: ui.LayoutNode = self._menu.root
        self.ln_edit_map: ui.LayoutNode = root.find_node('edit map')
        self.ln_edit_viewport: ui.LayoutNode = root.find_node('edit viewport')

        self.btn_edit_viewport: ui.Button = root.find_node('btn_edit_viewport').get_content()
        self.btn_edit_viewport.register_pressed_callback(partial(self.toggle_edit_viewport, True))
        self.btn_save_viewport: ui.Button = root.find_node('btn_save_viewport').get_content()
        self.btn_save_viewport.register_pressed_callback(partial(self.toggle_edit_viewport, False))

        self.lst_files: ui.UIList = root.find_node('lst_files').get_content()

        self.sld_isovalue: ui.Slider = root.find_node('sld_isovalue').get_content()
        self.sld_isovalue.register_changed_callback(self.update_isovalue_lbl)
        self.sld_isovalue.register_released_callback(self.redraw_map)

        self.sld_opacity: ui.Slider = root.find_node('sld_opacity').get_content()
        self.sld_opacity.register_changed_callback(self.update_opacity_lbl)
        self.sld_opacity.register_released_callback(self.update_color)

        self.sld_radius: ui.Slider = root.find_node('sld_radius').get_content()
        self.sld_radius.register_changed_callback(self.update_radius_lbl)
        self.sld_radius.register_released_callback(self.redraw_map)

        self.lbl_resolution: ui.Label = root.find_node('lbl_resolution').get_content()
        self.lbl_opacity: ui.Label = root.find_node('lbl_opacity').get_content()
        self.lbl_isovalue: ui.Label = root.find_node('lbl_isovalue').get_content()
        self.lbl_radius: ui.Label = root.find_node('lbl_radius').get_content()

        self.ln_isovalue_line: ui.LayoutNode = root.find_node('ln_isovalue_line')

        # self.btn_show_hide_map: ui.Button = root.find_node('btn_show_hide_map').get_content()
        # self.btn_show_hide_map.switch.active = True
        # self.btn_show_hide_map.toggle_on_press = True
        # self.btn_show_hide_map.register_pressed_callback(self.toggle_map_visibility)

        # self.btn_wireframe: ui.Button = root.find_node('btn_wireframe').get_content()
        # self.btn_wireframe.switch.active = True
        # self.btn_wireframe.toggle_on_press = True
        # self.btn_wireframe.register_pressed_callback(self.set_wireframe_mode)

        self.img_histogram: ui.Image = root.find_node('img_histogram').get_content()
        self.dd_color_scheme: ui.Dropdown = root.find_node('dd_color_scheme').get_content()
        self.dd_color_scheme.register_item_clicked_callback(self.update_color)

    def set_isovalue_ui(self, isovalue: float):
        self.sld_isovalue.current_value = isovalue
        self.update_isovalue_lbl(self.sld_isovalue)

    def set_opacity_ui(self, opacity: float):
        self.sld_opacity.current_value = opacity
        self.update_opacity_lbl(self.sld_opacity)

    def set_radius_ui(self, radius: float):
        self.sld_radius.current_value = radius
        self.update_radius_lbl(self.sld_radius)

    def update_isovalue_lbl(self, sld):
        self.lbl_isovalue.text_value = f'{round(sld.current_value, 2)} A'
        self._plugin.update_content(self.lbl_isovalue, sld)

        # /!\ calculation is sensitive to menu and image dimensions
        # position histogram line based on isovalue
        # plot width 800, left padding 100, right padding 80
        x_min = self.map_group.hist_x_min
        x_max = self.map_group.hist_x_max
        x = (sld.current_value - x_min) / (x_max - x_min)
        left = (100 + x * 620) / 800
        self.ln_isovalue_line.set_padding(left=left)
        self._plugin.update_node(self.ln_isovalue_line)

    def update_opacity_lbl(self, sld):
        self.lbl_opacity.text_value = str(round(100 * sld.current_value))
        self._plugin.update_content(self.lbl_opacity, sld)

    def update_radius_lbl(self, sld):
        self.lbl_radius.text_value = f'{round(sld.current_value, 2)} A'
        self._plugin.update_content(self.lbl_radius, sld)

    @async_callback
    async def toggle_edit_viewport(self, edit_viewport: bool, btn: ui.Button):
        self.ln_edit_map.enabled = not edit_viewport
        self.ln_edit_viewport.enabled = edit_viewport
        self._plugin.update_node(self.ln_edit_map, self.ln_edit_viewport)

        await self.viewport_editor.toggle_edit(edit_viewport)

        if not edit_viewport:
            self.redraw_map()

    @async_callback
    async def update_color(self, *args):
        color_scheme = self.color_scheme
        opacity = self.opacity
        await self.map_group.update_color(color_scheme, opacity)

    @async_callback
    async def redraw_map(self, content=None):
        if self.viewport_editor.is_editing:
            self.viewport_editor.update_radius(self.radius)
            return
        self.map_group.isovalue = self.isovalue
        self.map_group.opacity = self.opacity
        self.map_group.color_scheme = self.color_scheme
        self.map_group.radius = self.radius
        if self.map_group.mesh:
            await self.map_group.generate_mesh()

    @property
    def temp_dir(self):
        return self._plugin.temp_dir.name

    def render(self, map_group: MapGroup):
        self._menu.title = f'{map_group.group_name} Map'

        # Populate file list
        self.lst_files.items.clear()
        for filepath in map_group.files:
            ln = ui.LayoutNode()
            btn = ln.add_new_button()
            filename = os.path.basename(filepath)
            btn.text.value.set_all(filename)
            self.lst_files.items.append(ln)

        # Populate color scheme dropdown
        current_scheme = map_group.color_scheme
        for item in self.dd_color_scheme.items:
            if item.name.lower() == current_scheme.name.lower():
                item.selected = True
            else:
                item.selected = False

        # Generate histogram
        img_filepath = map_group.generate_histogram(self.temp_dir)
        self.img_histogram.file_path = img_filepath

        self.sld_isovalue.min_value = map_group.hist_x_min
        self.sld_isovalue.max_value = map_group.hist_x_max

        self.set_isovalue_ui(self.map_group.isovalue)
        self.set_opacity_ui(self.map_group.opacity)
        self.set_radius_ui(self.map_group.radius)

        self._plugin.update_menu(self._menu)

    @property
    def isovalue(self):
        return self.sld_isovalue.current_value

    @property
    def opacity(self):
        return self.sld_opacity.current_value

    @property
    def radius(self):
        return self.sld_radius.current_value

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

    # def set_wireframe_mode(self, btn):
    #     toggle = btn.selected
    #     Logs.message(f"Wireframe mode set to {toggle}")
    #     self.map_group.toggle_wireframe_mode(toggle)
    #     self.map_group.mesh.upload()

    # @async_callback
    # async def toggle_map_visibility(self, btn):
    #     toggle = btn.selected
    #     Logs.message(f"Map visibility set to {toggle}")
    #     opacity = self.opacity if toggle else 0
    #     color = self.map_group.color_scheme
    #     await self.map_group.update_color(color, opacity)
    #     self.map_group.mesh.upload()
