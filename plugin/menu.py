import asyncio
import aiohttp
import math
import nanome
import os
import requests
import time
import urllib
from functools import partial
from nanome.api import ui
from nanome.util import enums, Logs

from .models import MapGroup
from .utils import EMDBMetadataParser

import logging
logger = logging.getLogger(__name__)

ASSETS_PATH = os.path.join(os.path.dirname(f'{os.path.realpath(__file__)}'), 'assets')
MAIN_MENU_PATH = os.path.join(ASSETS_PATH, 'main_menu.json')
LOAD_FROM_EMDB_MENU_PATH = os.path.join(ASSETS_PATH, 'emdb_load_menu.json')
EDIT_MESH_MENU_PATH = os.path.join(ASSETS_PATH, 'edit_mesh_menu.json')
GROUP_ITEM_PATH = os.path.join(ASSETS_PATH, 'group_item.json')
DELETE_ICON = os.path.join(ASSETS_PATH, 'delete.png')
VISIBLE_ICON = os.path.join(ASSETS_PATH, 'visible.png')
INVISIBLE_ICON = os.path.join(ASSETS_PATH, 'invisible.png')

MAX_MAP_SIZE_KB = os.environ.get('MAX_MAP_SIZE_KB', 500000)

__all__ = ['MainMenu', 'EditMeshMenu']


class LoadFromEmdbMenu:

    def __init__(self, plugin_instance: nanome.PluginInstance):
        ui_manager = plugin_instance.ui_manager
        self._menu = ui_manager.create_new_menu(LOAD_FROM_EMDB_MENU_PATH)
        self._menu.index = 120  # arbitrary
        self._plugin = plugin_instance
        self.client = plugin_instance.client

        root: ui.LayoutNode = self._menu.root

        self.btn_rcsb_submit: ui.Button = root.find_node('btn_rcsb_submit').get_content()
        self.btn_embl_submit: ui.Button = root.find_node('btn_embl_submit').get_content()
        self.btn_rcsb_submit.disable_on_press = True
        self.btn_embl_submit.disable_on_press = True
        self.ti_rcsb_query: ui.TextInput = root.find_node('ti_rcsb_query').get_content()
        self.ti_embl_query: ui.TextInput = root.find_node('ti_embl_query').get_content()
        ui_manager.register_btn_pressed_callback(self.btn_rcsb_submit, self.on_rcsb_submit)
        ui_manager.register_btn_pressed_callback(self.btn_embl_submit, self.on_emdb_submit)
        self.lb_embl_download: ui.LoadingBar = root.find_node('lb_embl_download')
        # For development only
        # rcsb, embl = ['4znn', '3001']  # 94.33 degree unit cell
        rcsb, embl = ['', '8216']  # 111.55 degree unit cell  5k7n RCSB code
        # rcsb, embl = ['5vos', '8720']  # 100.02 degree unit cell
        # rcsb, embl = ['7c4u', '30288']  # small molecule
        # rcsb, embl = ['7q1u', '13764']  # large protein
        self.ti_rcsb_query.input_text = rcsb
        self.ti_embl_query.input_text = embl
        self.btn_browse_emdb: ui.Button = root.find_node('ln_btn_browse_emdb').get_content()
        ui_manager.register_btn_pressed_callback(self.btn_browse_emdb, self.on_browse_emdb)

    def render(self):
        self._menu.enabled = True
        self.client.update_menu(self._menu)

    def on_browse_emdb(self, btn):
        """Open the EMDB website in the user's browser"""
        base_search_url = "www.ebi.ac.uk/emdb/search"
        # query only low molecular weight maps, because download speeds are really bad.
        query = urllib.parse.quote('* AND overall_molecular_weight:{0 TO 50000]')
        query_params = urllib.parse.urlencode({
            'rows': 10,
            'sort': 'release_date desc'
        })
        url = f"{base_search_url}/{query}?{query_params}"
        self._plugin.client.open_url(url)

    async def on_rcsb_submit(self, btn):
        pdb_id = self.ti_rcsb_query.input_text
        Logs.debug(f"RCSB query: {pdb_id}")

        # Disable RCSB button
        self.btn_embl_submit.unusable = True
        self.btn_embl_submit.text.value.unusable = "Load"
        self._plugin.client.update_content(self.btn_embl_submit)

        pdb_path = self.download_pdb_from_rcsb(pdb_id)
        if not pdb_path:
            return
        await self._plugin.add_model_to_group(pdb_path)

        # Reenable embl search button
        self.btn_embl_submit.unusable = False
        self.btn_embl_submit.text.value.unusable = "Downloading..."
        self._plugin.client.update_content(self.btn_embl_submit, btn)

    async def on_emdb_submit(self, btn):
        embid_id = self.ti_embl_query.input_text
        Logs.debug(f"EMDB query: {embid_id}")

        # Disable RCSB button
        self.btn_rcsb_submit.unusable = True
        self.btn_rcsb_submit.text.value.unusable = "Load"
        self._plugin.client.update_content(self.btn_rcsb_submit)
        try:
            metadata_parser = self.download_metadata_from_emdbid(embid_id)
            # Validate file size is within limit.
            if metadata_parser.map_filesize > MAX_MAP_SIZE_KB:
                raise Exception
        except requests.exceptions.HTTPError:
            msg = "EMDB ID not found"
            Logs.warning(msg)
            self._plugin.client.send_notification(enums.NotificationTypes.error, msg)
        except Exception:
            msg = "Map file must be smaller than 500MB"
            self._plugin.client.send_notification(enums.NotificationTypes.error, msg)
        else:
            # Download map data
            map_file = await self.download_mapgz_from_emdbid(embid_id, metadata_parser)
            isovalue = metadata_parser.isovalue
            # Update message to say generating mesh
            self._plugin.client.update_content(btn)
            btn.text.value.unusable = "Generating..."
            btn.unusable = True
            self._plugin.client.update_content(btn)

            await self._plugin.add_mapfile_to_group(map_file, isovalue, metadata_parser)

            # Populate rcsb text input with pdb from metadata
            if metadata_parser.pdb_list:
                pdb_id = metadata_parser.pdb_list[0]
            else:
                pdb_id = ""
            self.ti_rcsb_query.input_text = pdb_id
            self._plugin.client.update_content(self.ti_rcsb_query)
        # Reenable rcsb load button
        self.btn_rcsb_submit.unusable = False
        self.btn_rcsb_submit.text.value.unusable = "Downloading..."
        btn.text.value.unusable = "Downloading..."
        btn.unusable = False
        self._plugin.client.update_content(self.btn_rcsb_submit, btn)

    @property
    def temp_dir(self):
        return self._plugin.temp_dir.name

    def download_pdb_from_rcsb(self, pdb_id):
        url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
        response = requests.get(url)
        if response.status_code != 200:
            Logs.warning(f"PDB for {pdb_id} not found")
            self._plugin.client.send_notification(
                nanome.util.enums.NotificationTypes.error,
                f"{pdb_id} not found in RCSB")
            return
        file_path = f'{self.temp_dir}/{pdb_id}.pdb'
        with open(file_path, 'wb') as f:
            f.write(response.content)
        return file_path

    def download_metadata_from_emdbid(self, emdbid):
        Logs.debug("Downloading metadata for EMDBID:", emdbid)
        url = f"https://ftp.ebi.ac.uk/pub/databases/emdb/structures/EMD-{emdbid}/header/emd-{emdbid}.xml"
        response = requests.get(url)
        response.raise_for_status()
        return EMDBMetadataParser(response.content)

    async def download_mapgz_from_emdbid(self, emdbid, metadata_parser: EMDBMetadataParser):
        Logs.message("Downloading map data from EMDB:", emdbid)
        url = f"https://ftp.ebi.ac.uk/pub/databases/emdb/structures/EMD-{emdbid}/map/emd_{emdbid}.map.gz"
        # Write the map to a .map file
        file_path = f'{self.temp_dir}/{emdbid}.map.gz'
        # Set up loading bar
        self.lb_embl_download.enabled = True
        self._plugin.client.update_node(self.lb_embl_download)
        loading_bar = self.lb_embl_download.get_content()

        async with aiohttp.ClientSession() as session:
            # Get content size from head request
            response = await session.head(url)
            file_size = int(response.headers['Content-Length']) / 1000

            chunk_size = 8192
            async with session.get(url) as response:
                with open(file_path, 'wb') as file:
                    start_time = time.time()
                    data_check = start_time
                    downloaded_chunks = 0
                    while True:
                        chunk = await response.content.read(chunk_size)
                        if not chunk:
                            break
                        downloaded_chunks += len(chunk)
                        file.write(chunk)
                        now = time.time()
                        # Update UI with download progress
                        ui_update_interval = 3
                        if now - data_check > ui_update_interval:
                            kb_downloaded = downloaded_chunks / 1000
                            Logs.debug(f"{int(now - start_time)} seconds: {kb_downloaded} / {file_size} kbs")
                            loading_bar.percentage = kb_downloaded / file_size
                            self.btn_embl_submit.text.value.unusable = \
                                f"Downloading... ({int(kb_downloaded/1000)}/{int(file_size/1000)} MB)"
                            self.btn_embl_submit.unusable = True
                            self._plugin.client.update_content(loading_bar, self.btn_embl_submit)
                            data_check = now
        loading_bar.percentage = 0
        self.lb_embl_download.enabled = False
        self._plugin.client.update_node(self.lb_embl_download)
        return file_path


class MainMenu:

    def __init__(self, plugin_instance: nanome.PluginInstance):
        ui_manager = plugin_instance.ui_manager
        self._menu = ui_manager.create_new_menu(MAIN_MENU_PATH)
        self._plugin = plugin_instance

        self.pfb_group_item: ui.LayoutNode = ui.LayoutNode.io.from_json(GROUP_ITEM_PATH)
        self.pfb_group_item.find_node('Button Delete').get_content().icon.value.set_all(DELETE_ICON)

        root: ui.LayoutNode = self._menu.root
        self.lst_groups: ui.UIList = root.find_node('lst_groups').get_content()

        self.btn_add_group: ui.Button = root.find_node('ln_btn_add_group').get_content()
        ui_manager.register_btn_pressed_callback(self.btn_add_group, self.add_mapgroup)

        self.btn_load_from_emdb: ui.Button = root.find_node('ln_btn_load_from_emdb').get_content()
        ui_manager.register_btn_pressed_callback(self.btn_load_from_emdb, self.open_emdb_menu)

        self.btn_load_from_vault: ui.Button = root.find_node('ln_btn_load_from_vault').get_content()
        ui_manager.register_btn_pressed_callback(self.btn_load_from_vault, self.open_vault_menu)

    async def render(self, force_enable=False, selected_mapgroup=None):
        if force_enable:
            self._menu.enabled = True

        groups = self._plugin.groups
        # By default, select the first group
        if groups and not selected_mapgroup:
            selected_mapgroup = groups[0]
        self.render_map_groups(groups, selected_mapgroup)
        self._plugin.client.update_menu(self._menu)

    def open_emdb_menu(self, btn):
        self.emdb_menu = LoadFromEmdbMenu(self._plugin)
        self.emdb_menu.render()
        pass

    def open_vault_menu(self, btn):
        self._plugin.vault_menu.show_menu()

    @property
    def temp_dir(self):
        return self._plugin.temp_dir.name

    def add_mapgroup(self, btn):
        Logs.message('Adding new map group')
        self._plugin.add_mapgroup()
        asyncio.create_task(self.render())

    def render_map_groups(self, mapgroups, selected_mapgroup=None):
        self.lst_groups.items.clear()
        for map_group in mapgroups:
            ln: ui.LayoutNode = self.pfb_group_item.clone()
            lbl: ui.Label = ln.find_node('Label').get_content()

            btn_add_to_map: ui.Button = ln.find_node('ln_btn_add_to_map').get_content()
            btn_add_to_map.toggle_on_press = True
            self._plugin.ui_manager.register_btn_pressed_callback(
                btn_add_to_map, self.select_mapgroup)
            btn_add_to_map.selected = map_group == selected_mapgroup
            lbl.text_value = map_group.group_name

            ln_group_details = ln.find_node('ln_group_details')
            edit_mesh_btn: ui.Button = ln_group_details.get_content()
            self._plugin.ui_manager.register_btn_pressed_callback(
                edit_mesh_btn,
                partial(self.open_edit_mesh_menu, map_group))

            btn_delete: ui.Button = ln.find_node('Button Delete').get_content()
            self._plugin.ui_manager.register_btn_pressed_callback(
                btn_delete,
                partial(self.delete_group, map_group))

            btn_toggle: ui.Button = ln.find_node('Button Toggle').get_content()
            btn_toggle.icon.value.set_all(
                VISIBLE_ICON if map_group.visible else INVISIBLE_ICON)
            self._plugin.ui_manager.register_btn_pressed_callback(
                btn_toggle,
                partial(self.toggle_group, map_group))

            self.lst_groups.items.append(ln)
        self._plugin.client.update_content(self.lst_groups)

    def select_mapgroup(self, selected_btn: ui.Button):
        Logs.message('Selecting map group')
        for item in self.lst_groups.items:
            btn: ui.Button = item.find_node('ln_btn_add_to_map').get_content()
            btn.selected = btn._content_id == selected_btn._content_id
        self._plugin.client.update_content(self.lst_groups)

    def get_selected_mapgroup(self):
        for item in self.lst_groups.items:
            btn: ui.Button = item.find_node('ln_btn_add_to_map').get_content()
            if btn.selected:
                label = item.find_node('Label').get_content()
                return label.text_value

    async def open_edit_mesh_menu(self, map_group, btn=None):
        if not map_group.has_map():
            msg = "Please add Map from EMDB before opening menu"
            await self._plugin.client.send_notification(enums.NotificationTypes.warning, msg)
            Logs.warning('Tried to open menu before adding map.')
            return
        Logs.message('Loading group details menu')
        edit_mesh_menu = EditMeshMenu(map_group, self._plugin)
        edit_mesh_menu.render(map_group)

    async def delete_group(self, map_group, btn):
        Logs.message(f'Deleting group {map_group.group_name}')
        await self._plugin.delete_mapgroup(map_group)

    def toggle_group(self, map_group, btn: ui.Button):
        Logs.message('Toggling group')
        map_group.visible = not map_group.visible
        btn.icon.value.set_all(
            VISIBLE_ICON if map_group.visible else INVISIBLE_ICON)
        self._plugin.client.update_content(btn)
        self._plugin.client.update_structures_shallow([map_group.map_mesh.complex, map_group.model_complex])


class EditMeshMenu:

    # used to scale the isovalue slider when values are too small for slider to work with
    isovalue_scaling_factor = 100

    def __init__(self, map_group, plugin_instance: nanome.PluginInstance):
        self.map_group = map_group
        self._plugin = plugin_instance

        ui_manager = self._plugin.ui_manager
        self._menu = ui_manager.create_new_menu(EDIT_MESH_MENU_PATH)
        self._menu.index = 20

        root: ui.LayoutNode = self._menu.root
        self.ln_edit_map: ui.LayoutNode = root.find_node('edit map')
        self.lst_files: ui.UIList = root.find_node('lst_files').get_content()
        self.btn_redraw_map = root.find_node('ln_btn_redraw_map').get_content()
        self.btn_redraw_map.disable_on_press = True
        ui_manager.register_btn_pressed_callback(self.btn_redraw_map, self.redraw_new_isovalue)
        self.sld_isovalue: ui.Slider = root.find_node('sld_isovalue').get_content()
        ui_manager.register_slider_change_callback(self.sld_isovalue, self.update_isovalue_lbl)

        self.sld_opacity: ui.Slider = root.find_node('sld_opacity').get_content()
        ui_manager.register_slider_change_callback(self.sld_opacity, self.update_opacity_lbl)
        ui_manager.register_slider_released_callback(self.sld_opacity, self.update_color)

        self.lbl_resolution: ui.Label = root.find_node('lbl_resolution').get_content()
        self.lbl_opacity: ui.Label = root.find_node('lbl_opacity').get_content()
        self.lbl_isovalue: ui.Label = root.find_node('lbl_isovalue').get_content()

        self.ln_isovalue_line: ui.LayoutNode = root.find_node('ln_isovalue_line')

        self.ln_img_histogram: ui.LayoutNode = root.find_node('img_histogram')
        self.dd_color_scheme: ui.Dropdown = root.find_node('dd_color_scheme').get_content()
        ui_manager.register_dropdown_item_clicked_callback(self.dd_color_scheme, self.set_color_scheme)

        self.btn_show_full_map: ui.Button = root.find_node('btn_show_full_map').get_content()
        self.btn_show_full_map.disable_on_press = True
        ui_manager.register_btn_pressed_callback(
            self.btn_show_full_map, self.show_full_map)

        self.btn_box_around_model: ui.Button = root.find_node('btn_box_around_model').get_content()
        self.btn_box_around_model.disable_on_press = True
        ui_manager.register_btn_pressed_callback(
            self.btn_box_around_model, self.box_map_around_model)

        self.btn_box_around_selection: ui.Button = root.find_node('btn_box_around_selection').get_content()
        self.btn_box_around_selection.disable_on_press = True
        ui_manager.register_btn_pressed_callback(
            self.btn_box_around_selection, self.box_map_around_selection)

    def render(self, map_group: MapGroup):
        isovalue = map_group.isovalue or 0
        self._menu.title = f'{map_group.group_name} Map (Primary Contour: {round(isovalue, 3)})'
        # Populate file list
        self.lst_files.items.clear()
        group_objs = []
        if map_group.mapfile:
            map_comp = map_group.map_mesh.complex
            group_objs.append(map_comp)
        if map_group.model_complex:
            group_objs.append(map_group.model_complex)

        for comp in group_objs:
            ln = ui.LayoutNode()
            btn = ln.add_new_button()
            btn.unusable = True
            btn.text.value.set_all(comp.full_name)
            btn.comp = comp
            btn.toggle_on_press = True
            self.lst_files.items.append(ln)

        # Populate color scheme dropdown
        current_scheme = map_group.color_scheme
        for item in self.dd_color_scheme.items:
            if item.name.lower() == current_scheme.name.lower():
                item.selected = True
            else:
                item.selected = False
        if map_group.metadata:
            resolution = map_group.metadata.resolution
            self.lbl_resolution.text_value = f'{resolution} A' if resolution else ''
        self.set_isovalue_ui(self.map_group)
        self.set_opacity_ui(self.map_group.opacity)

        if map_group.has_map():
            self.set_isovalue_slider_min_max(map_group)
        if map_group.has_map() and not map_group.png_tempfile:
            self.ln_img_histogram.add_new_label('Loading Contour Histogram...')

        color_scheme_text = f"Color Scheme ({self.color_scheme.name})"
        self.dd_color_scheme.permanent_title = color_scheme_text
        self._plugin.client.update_menu(self._menu)
        if map_group.has_map() and not map_group.png_tempfile:
            # Generate histogram and add to menu.
            map_group.generate_histogram(self.temp_dir)
            self.set_isovalue_slider_min_max(map_group)
            self._plugin.client.update_content(self.sld_isovalue)
        if map_group.png_tempfile:
            self.ln_img_histogram.add_new_image(map_group.png_tempfile.name)
        self._plugin.client.update_node(self.ln_img_histogram)

    def set_isovalue_ui(self, map_group):
        self.set_isovalue_slider_min_max(map_group)
        self.update_isovalue_lbl(self.sld_isovalue)

    def set_opacity_ui(self, opacity: float):
        self.sld_opacity.current_value = opacity
        self.update_opacity_lbl(self.sld_opacity)

    def update_isovalue_lbl(self, sld):
        slider_value = self.get_isovalue_from_slider()
        self.lbl_isovalue.text_value = f'{round(slider_value, 3)} A'
        self._plugin.client.update_content(self.lbl_isovalue, sld)

        # /!\ calculation is sensitive to menu and image dimensions
        # position histogram line based on isovalue
        # plot width 800, left padding 100, right padding 80
        if self.map_group.has_histogram():
            x_min = self.map_group.hist_x_min
            x_max = self.map_group.hist_x_max
            current_value = self.get_isovalue_from_slider()
            x = (current_value - x_min) / (x_max - x_min)
            left = (100 + x * 620) / 800
            self.ln_isovalue_line.set_padding(left=left)
            self._plugin.client.update_node(self.ln_isovalue_line)

    def update_opacity_lbl(self, sld):
        self.lbl_opacity.text_value = str(round(100 * sld.current_value))
        self._plugin.client.update_content(self.lbl_opacity, sld)

    def sld_radius_update(self, sld):
        sld_current_val = sld.current_value
        self.lbl_radius.text_value = f'{round(sld_current_val, 2)} A'
        self._plugin.client.update_content(self.lbl_radius, sld)

    async def show_full_map(self, btn):
        Logs.message("Showing full map...")
        await self.map_group.generate_full_mesh()
        self._plugin.client.update_content(btn)

    async def box_map_around_selection(self, btn: ui.Button):
        Logs.message("Extracting map around selection...")
        await self.map_group.generate_mesh_around_selection()
        self._plugin.client.update_content(btn)

    async def box_map_around_model(self, btn):
        Logs.message("Extracting map around model...")
        await self.map_group.generate_mesh_around_model()
        self._plugin.client.update_content(btn)

    async def update_color(self, *args):
        color_scheme = self.color_scheme
        opacity = self.opacity
        await self.map_group.update_color(color_scheme, opacity)

    async def redraw_map(self, btn=None):
        self.map_group.isovalue = self.get_isovalue_from_slider()
        self.map_group.opacity = self.opacity
        self.map_group.color_scheme = self.color_scheme
        if self.map_group.has_map():
            await self.map_group.redraw_mesh()

    async def redraw_new_isovalue(self, btn):
        rendered_isovalue = self.sld_isovalue.current_value
        await self.redraw_map(btn)
        # Set slider back to initial value, in case user
        # moved it while map was being redrawn
        self.sld_isovalue.current_value = rendered_isovalue
        self._plugin.client.update_content(btn, self.sld_isovalue)

    @property
    def temp_dir(self):
        return self._plugin.temp_dir.name

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

    async def set_color_scheme(self, *args):
        self.dd_color_scheme.permanent_title = f"Color Scheme ({self.color_scheme.name})"
        self._plugin.client.update_content(self.dd_color_scheme)
        await self.map_group.update_color(self.color_scheme, self.opacity)

    def set_isovalue_slider_min_max(self, map_group):
        min_value = map_group.hist_x_min
        max_value = map_group.hist_x_max
        # Handle weird slider edge cases where isovalue isn't set, or min/max are infinite
        if map_group.isovalue is not None:
            current_value = map_group.isovalue
        elif not math.isinf(min_value) and not math.isinf(max_value):
            current_value = (min_value + max_value) / 2
        else:
            current_value = 0
        # Scale isovalue if histogram range is too small for UI slider to handle
        if map_group.has_small_histogram_range():
            min_value = min_value * self.isovalue_scaling_factor
            max_value = max_value * self.isovalue_scaling_factor
            current_value = current_value * self.isovalue_scaling_factor
        self.sld_isovalue.min_value = min_value
        self.sld_isovalue.max_value = max_value
        self.sld_isovalue.current_value = current_value

    def get_isovalue_from_slider(self):
        isovalue = self.sld_isovalue.current_value
        if self.map_group.has_small_histogram_range():
            isovalue = isovalue / self.isovalue_scaling_factor
        return isovalue
