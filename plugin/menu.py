import nanome
import requests
import time
import xml.etree.ElementTree as ET
from functools import partial
from nanome.api import ui
from nanome.util import async_callback, enums, Logs
from os import path

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
        # By default, select the first group
        if groups and not selected_mapgroup:
            selected_mapgroup = groups[0]
        self.render_map_groups(groups, selected_mapgroup)
        self._plugin.update_menu(self._menu)

    def add_mapgroup(self, btn):
        Logs.message('Adding new map group')
        self._plugin.add_mapgroup()
        self.render()

    def on_btn_search_menu_pressed(self, btn):
        Logs.message('Loading Search menu')
        self._plugin.enable_search_menu()

    def render_map_groups(self, mapgroups, selected_mapgroup=None):
        self.lst_groups.items.clear()
        for map_group in mapgroups:
            ln: ui.LayoutNode = self.pfb_group_item.clone()
            lbl: ui.Label = ln.find_node('Label').get_content()

            btn_add_to_map: ui.Button = ln.find_node('ln_btn_add_to_map').get_content()
            btn_add_to_map.toggle_on_press = True
            btn_add_to_map.register_pressed_callback(self.select_mapgroup)
            btn_add_to_map.selected = map_group == selected_mapgroup
            lbl.text_value = map_group.group_name

            btn: ui.Button = ln.get_content()
            btn.register_pressed_callback(partial(self.open_edit_mesh_menu, map_group))

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

    def get_selected_mapgroup(self):
        for item in self.lst_groups.items:
            btn: ui.Button = item.find_node('ln_btn_add_to_map').get_content()
            if btn.selected:
                label = item.find_node('Label').get_content()
                return label.text_value

    def open_edit_mesh_menu(self, map_group, btn=None):
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
        self.btn_rcsb_submit.disable_on_press = True
        self.btn_embl_submit.disable_on_press = True

        self.ti_rcsb_query: ui.TextInput = root.find_node('ti_rcsb_query').get_content()
        self.ti_embl_query: ui.TextInput = root.find_node('ti_embl_query').get_content()

        self.btn_rcsb_submit.register_pressed_callback(self.on_rcsb_submit)
        self.btn_embl_submit.register_pressed_callback(self.on_embl_submit)
        self.lb_embl_download: ui.LoadingBar = root.find_node('lb_embl_download')
        self.current_group = "Group 1"
        # For development only
        # rcsb, embl = ['4znn', '3001']  # 94.33º
        rcsb, embl = ['5k7n', '8216']  # 111.55º
        # rcsb, embl = ['5vos', '8720']  # 100.02º
        # rcsb, embl = ['7c4u', '30288']  # small molecule
        # rcsb, embl = ['7q1u', '13764']  # large protein
        self.ti_rcsb_query.input_text = rcsb
        self.ti_embl_query.input_text = embl

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

        # Disable RCSB button
        self.btn_embl_submit.unusable = True
        self.btn_embl_submit.text.value.unusable = "Search"
        self._plugin.update_content(self.btn_embl_submit)

        pdb_path = self.download_pdb_from_rcsb(pdb_id)
        if not pdb_path:
            return
        await self._plugin.add_pdb_to_group(pdb_path)

        # Reenable embl search button
        self.btn_rcsb_submit.unusable = False
        self.btn_rcsb_submit.text.value.unusable = "Downloading..."
        self._plugin.update_content(self.btn_embl_submit, btn)

    @async_callback
    async def on_embl_submit(self, btn):
        embid_id = self.ti_embl_query.input_text
        Logs.debug(f"EMBL query: {embid_id}")

        # Disable RCSB button
        self.btn_rcsb_submit.unusable = True
        self.btn_rcsb_submit.text.value.unusable = "Search"
        self._plugin.update_content(self.btn_rcsb_submit)

        metadata = self.download_metadata_from_emdbid(embid_id)
        map_file = self.download_cryoem_map_from_emdbid(embid_id, metadata)
        isovalue = self.get_isovalue_from_metadata(metadata)
        await self._plugin.add_mapgz_to_group(map_file, isovalue, metadata)
        # Reenable rcsb search button
        self.btn_rcsb_submit.unusable = False
        self.btn_rcsb_submit.text.value.unusable = "Downloading..."
        self._plugin.update_content(self.btn_rcsb_submit, btn)

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

    def download_metadata_from_emdbid(self, emdbid):
        Logs.message("Downloading EM metadata for EMDBID:", emdbid)
        url = f"https://ftp.ebi.ac.uk/pub/databases/emdb/structures/EMD-{emdbid}/header/emd-{emdbid}.xml"
        response = requests.get(url)
        return ET.fromstring(response.content)

    def get_isovalue_from_metadata(self, xml_root):
        # Parse xml and get isovalue
        contour_list_ele = next(xml_root.iter("contour_list"))
        for child in contour_list_ele:
            if child.tag == "contour" and child.attrib["primary"].lower() == 'true':
                level_ele = next(child.iter("level"))
                isovalue = level_ele.text
                break
        try:
            isovalue = float(isovalue)
        except ValueError:
            Logs.warning("Could not parse isovalue from XML")
            isovalue = None
        return isovalue

    def get_filesize_from_metadata(self, xml_root):
        # Parse xml and get isovalue
        map_tag = next(xml_root.iter("map"))
        size_kbytes = map_tag.attrib.get("size_kbytes", None)
        try:
            filesize = int(size_kbytes)
        except ValueError:
            Logs.warning("Could not parse isovalue from XML")
            filesize = None
        return filesize

    def download_cryoem_map_from_emdbid(self, emdbid, metadata=None):
        Logs.message("Downloading map data from EMDB:", emdbid)
        url = f"https://ftp.ebi.ac.uk/pub/databases/emdb/structures/EMD-{emdbid}/map/emd_{emdbid}.map.gz"
        # Write the map to a .map file
        file_path = f'{self.temp_dir}/{emdbid}.map.gz'
        # Set up loading bar
        self.lb_embl_download.enabled = True
        self._plugin.update_node(self.lb_embl_download)
        loading_bar = self.lb_embl_download.get_content()

        file_size = self.get_filesize_from_metadata(metadata)
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            chunk_size = 8192
            downloaded_chunks = 0
            with open(file_path, "wb") as f:
                start_time = time.time()
                data_check = start_time
                for chunk in r.iter_content(chunk_size=chunk_size):
                    downloaded_chunks += chunk_size
                    f.write(chunk)
                    now = time.time()
                    if now - data_check > 5:
                        kb_downloaded = downloaded_chunks / 1000
                        Logs.debug(f"{int(now - start_time)} seconds: kbs downloaded: {kb_downloaded}")
                        loading_bar.percentage = kb_downloaded / file_size
                        self._plugin.update_content(loading_bar)
                        data_check = now
        self.lb_embl_download.enabled = False
        self._plugin.update_node(self.lb_embl_download)
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

        self.ln_img_histogram: ui.LayoutNode = root.find_node('img_histogram')
        self.dd_color_scheme: ui.Dropdown = root.find_node('dd_color_scheme').get_content()
        self.dd_color_scheme.register_item_clicked_callback(self.update_color)
        self.btn_zoom: ui.Button = root.find_node('btn_zoom').get_content()
        self.btn_zoom.register_pressed_callback(self.zoom_to_struct)

        self.btn_delete: ui.Button = root.find_node('btn_delete').get_content()
        self.btn_delete.register_pressed_callback(self.delete_group_objects)

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
    async def redraw_map(self, btn=None):
        if self.viewport_editor.is_editing:
            self.viewport_editor.update_radius(self.radius)
            return
        self.map_group.isovalue = self.isovalue
        self.map_group.opacity = self.opacity
        self.map_group.color_scheme = self.color_scheme
        self.map_group.radius = self.radius
        if self.map_group.has_map():
            await self.map_group.generate_mesh()

    @property
    def temp_dir(self):
        return self._plugin.temp_dir.name

    def render(self, map_group: MapGroup):
        self._menu.title = f'{map_group.group_name} Map'

        # Populate file list
        self.lst_files.items.clear()

        group_objs = []
        if map_group.map_gz_file:
            map_comp = map_group.map_mesh.complex
            group_objs.append(map_comp)
        if map_group.model_complex:
            group_objs.append(map_group.model_complex)

        for comp in group_objs:
            ln = ui.LayoutNode()
            btn = ln.add_new_button()
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
            resolution = self.get_resolution_from_metadata(map_group.metadata)
            self.lbl_resolution.text_value = f'{resolution} A' if resolution else ''
        self.set_isovalue_ui(self.map_group.isovalue)
        self.set_opacity_ui(self.map_group.opacity)
        self.set_radius_ui(self.map_group.radius)

        self._plugin.update_menu(self._menu)
        if map_group.has_map() and not map_group.png_tempfile:
            Logs.debug("Generating histogram...")
            self.ln_img_histogram.add_new_label('Loading Histogram...')
            self._plugin.update_node(self.ln_img_histogram)
            map_group.generate_histogram(self.temp_dir)
            Logs.debug("Histogram generated")
        if map_group.png_tempfile:
            self.ln_img_histogram.add_new_image(map_group.png_tempfile.name)
        self.sld_isovalue.min_value = map_group.hist_x_min
        self.sld_isovalue.max_value = map_group.hist_x_max
        self._plugin.update_node(self.ln_img_histogram)
        self._plugin.update_content(self.sld_isovalue)

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

    def zoom_to_struct(self, btn: ui.Button):
        strucs = []
        for item in self.lst_files.items:
            item_btn = item.get_content()
            if item_btn.selected:
                item_comp = getattr(item_btn, 'comp', None)
                if item_comp:
                    strucs.append(item_comp)
        self._plugin.zoom_on_structures(strucs)

    def delete_group_objects(self, btn: ui.Button):
        Logs.message("Delete group objects button clicked.")
        strucs = []
        for item in self.lst_files.items:
            item_btn = item.get_content()
            if item_btn.selected:
                item_comp = getattr(item_btn, 'comp', None)
                if item_comp:
                    strucs.append(item_comp)
        if strucs:
            Logs.message(f"Deleting {len(strucs)} group objects.")
            self.map_group.remove_group_objects(strucs)
            self.render(self.map_group)

    def get_resolution_from_metadata(self, metadata: ET.ElementTree):
        # Parse xml and get isovalue
        final_reconstruction_ele = next(metadata.iter("final_reconstruction"))
        resolution_text = ""
        for child in final_reconstruction_ele:
            if child.tag == "resolution":
                res_ele = next(child.iter("resolution"))
                resolution_text = res_ele.text
                break
        try:
            resolution = float(resolution_text)
        except ValueError:
            Logs.warning("Could not parse resolution from XML")
            resolution = None
        return resolution
