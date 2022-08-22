import nanome
import requests
import tempfile
from os import path
from nanome.api import ui
from nanome.util import Logs, enums
import numpy as np

BASE_PATH = path.dirname(f'{path.realpath(__file__)}')
MAIN_MENU_PATH = path.join(BASE_PATH, 'main_menu.json')

MAP_FILETYPES = ['.map', '.map.gz']


class MainMenu:
    nanome_complex = None

    def __init__(self, plugin_instance):
        self._menu = ui.Menu.io.from_json(MAIN_MENU_PATH)
        self._plugin = plugin_instance
        self.ti_pdb_id.register_submitted_callback(self.download_pdb)
        self.sl_iso_value.register_released_callback(self.update_isosurface)
        self.sl_opacity.register_released_callback(self.update_opacity)
        self.sl_range_limit.register_released_callback(
            self.update_limited_view_range
        )
        self.dd_color_scheme.register_item_clicked_callback(
            self.change_color_scheme)
        self.btn_show_hide_map.register_pressed_callback(self.show_hide_map)
        self.btn_wireframe.register_pressed_callback(self.set_wireframe_mode)
        self.dd_complexes.register_item_clicked_callback(self.set_target_complex)
        self.dd_vault_mol_files.register_item_clicked_callback(self.set_selected_file)
        self.dd_vault_map_files.register_item_clicked_callback(self.set_selected_map_file)
        self.btn_show_hide_map.switch.active = True
        self.btn_show_hide_map.toggle_on_press = True
        self.btn_wireframe.switch.active = True
        self.btn_wireframe.toggle_on_press = True
        self.color_by = enums.ColorScheme.BFactor
        self.shown = self.btn_show_hide_map.selected

    @property
    def img_histo(self):
        return self._menu.root.find_node('img_histo').get_content()

    @property
    def dd_complexes(self):
        return self._menu.root.find_node('dd_complexes').get_content()

    @property
    def dd_vault_mol_files(self):
        return self._menu.root.find_node('dd_vault_mol_files').get_content()

    @property
    def dd_vault_map_files(self):
        return self._menu.root.find_node('dd_vault_map_files').get_content()

    @property
    def sl_iso_value(self):
        return self._menu.root.find_node('sl_iso_value').get_content()

    @property
    def sl_opacity(self):
        return self._menu.root.find_node('sl_opacity').get_content()

    @property
    def sl_range_limit(self):
        return self._menu.root.find_node('sl_range_limit').get_content()

    @property
    def dd_color_scheme(self):
        return self._menu.root.find_node('dd_color_scheme').get_content()

    @property
    def btn_show_hide_map(self):
        return self._menu.root.find_node('btn_show_hide_map').get_content()

    @property
    def btn_wireframe(self):
        return self._menu.root.find_node('btn_wireframe').get_content()

    @property
    def ti_pdb_id(self):
        return self._menu.root.find_node('ti_pdb_id').get_content()

    @property
    def lbl_iso_value(self):
        return self._menu.root.find_node('lbl_iso_value').get_content()

    @property
    def lbl_opacity_value(self):
        return self._menu.root.find_node('lbl_opacity_value').get_content()

    @property
    def lbl_limit_range_value(self):
        return self._menu.root.find_node('lbl_limit_range_value').get_content()

    @property
    def nanome_mesh(self):
        return self._plugin.nanome_mesh

    def render(self, ws):
        Logs.message("Enabling menu")
        self._menu.enabled = True
        self._plugin.update_menu(self._menu)
        self.dd_complexes.items = [
            nanome.ui.DropdownItem(c.name)
            for c in ws.complexes
        ]
        self.dd_vault_mol_files.items = [
            nanome.ui.DropdownItem(file["name"])
            for file in self._plugin.user_files
            if file["name"] not in MAP_FILETYPES
        ]

        self.dd_vault_map_files.items = [
            nanome.ui.DropdownItem(file["name"])
            for file in self._plugin.user_files
            if file["name"] in MAP_FILETYPES
        ]

        self.dd_color_scheme.items = [
            nanome.ui.DropdownItem(name)
            for name in ["Bfactor", "Element", "Chain"]
        ]
        self.dd_color_scheme.items[0].selected = True

        self.lbl_iso_value.text_value = str(round(self.sl_iso_value.current_value, 2))
        self.lbl_opacity_value.text_value = str(round(self.sl_opacity.current_value, 2))
        self.lbl_limit_range_value.text_value = str(round(self.sl_range_limit.current_value, 2))
        self._plugin.update_menu(self._menu)

    def download_cryoem_map_from_emdbid(self, emdbid):
        Logs.message("Downloading EM data for EMDBID:", emdbid)
        self._plugin.send_notification(
            nanome.util.enums.NotificationTypes.message, "Downloading EM data"
        )

        new_url = (
            "https://files.rcsb.org/pub/emdb/structures/"
            + emdbid
            + "/map/"
            + emdbid.lower().replace("-", "_")
            + ".map.gz"
        )

        # Write the map to a .map file
        with requests.get(new_url, stream=True) as r:
            r.raise_for_status()
            map_tempfile = tempfile.NamedTemporaryFile(
                delete=False, suffix=".map.gz"
            )
            with open(map_tempfile.name, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            self._plugin.map_file = map_tempfile
            self._plugin.load_map()
            self._plugin.generate_histogram()
            self._plugin.request_workspace(
                self._plugin.set_current_complex_generate_surface)

    def download_cryoem_map_from_pdbid(self, file):
        Logs.message("Downloading EM data for PDBID:", self.pdbid)
        self._plugin.send_notification(
            nanome.util.enums.NotificationTypes.message, "Downloading EM data"
        )
        base = "https://data.rcsb.org/rest/v1/core/entry/"
        rest_url = base + self.pdbid
        response = requests.get(rest_url)
        if response.status_code != 200:
            Logs.error("Something went wrong fetching the EM data")
            self._plugin.send_notification(
                nanome.util.enums.NotificationTypes.error,
                "No EMDB data for " + str(self.pdbid),
            )
            return
        result = response.json()
        k1 = "rcsb_entry_container_identifiers"
        k2 = "emdb_ids"
        if not k1 in result or not k2 in result[k1]:
            Logs.error("No EM data found for", self.pdbid)
            self._plugin.send_notification(
                nanome.util.enums.NotificationTypes.error,
                "No EMDB data for " + str(self.pdbid),
            )
            return
        emdb_ids = result[k1][k2]

        if "pdbx_vrpt_summary" in result and "contour_level_primary_map" in result["pdbx_vrpt_summary"]:
            self.map_prefered_level = float(
                result["pdbx_vrpt_summary"]["contour_level_primary_map"])
            Logs.debug("Found prevered level =", self.map_prefered_level)

        if len(emdb_ids) >= 1:
            self.download_cryoem_map_from_emdbid(emdb_ids[0])
        else:
            Logs.error("No EM data found for", self.pdbid)
            self._plugin.send_notification(
                nanome.util.enums.NotificationTypes.error,
                "No EMDB data for ",
                self.pdbid,
            )

    def download_pdb(self, textinput):
        self.current_mesh = []
        if self.nanome_mesh is not None:
            self.nanome_mesh.destroy()

        self.pdbid = textinput.input_text.strip()

        if self.nanome_complex is None and len(self.pdbid) != 4:
            Logs.error("Wrong PDBID:", self.pdbid)
            self._plugin.send_notification(
                nanome.util.enums.NotificationTypes.error, "Wrong PDB ID"
            )
            return False
        # Download the PDB only if no target complex set
        if self.nanome_complex is not None:
            if len(self.pdbid) == 4:
                self.download_cryoem_map_from_pdbid(None)
            else:
                if len(self.pdbid) > 4 and not "EMD" in self.pdbid and not "emd" in self.pdbid:
                    self.pdbid = "EMD-" + self.pdbid
                self.download_cryoem_map_from_emdbid(self.pdbid)
            return True

        base = "https://files.rcsb.org/download/"
        full_url = base + self.pdbid + ".pdb.gz"
        self._plugin.send_notification(
            nanome.util.enums.NotificationTypes.message, "Downloading PDB"
        )
        Logs.message("Downloading PDB file from", full_url)

        response = requests.get(full_url)
        if response.status_code != 200:
            Logs.error("Something went wrong fetching the PDB file")
            self._plugin.send_notification(
                nanome.util.enums.NotificationTypes.error, "Wrong PDB ID"
            )
            return False
        pdb_tempfile = tempfile.NamedTemporaryFile(
            delete=False, prefix="CryoEM_plugin_" + self.pdbid, suffix=".pdb.gz"
        )
        open(pdb_tempfile.name, "wb").write(response.content)
        pdb_path = pdb_tempfile.name.replace("\\", "/")
        self._plugin.send_files_to_load(pdb_path, self.download_cryoem_map_from_pdbid)
        return True

    def show_hide_map(self, toggle):
        opacity = self.sl_opacity.current_value
        if self.nanome_mesh is not None:
            self.nanome_mesh.color.a = int(
                opacity * 255) if toggle.selected else 0
            self.shown = toggle.selected
            self.nanome_mesh.upload()

    def set_wireframe_mode(self, toggle):
        self.wireframe_mode = toggle.selected
        if self.nanome_mesh is not None:
            if self.wireframe_mode:
                self.wire_vertices, wire_normals, self.wire_triangles = self.wireframe_mesh()
                self.nanome_mesh.vertices = self.wire_vertices.flatten()
                self.nanome_mesh.triangles = self.wire_triangles.flatten()
            else:
                self.nanome_mesh.vertices = np.asarray(self.computed_vertices).flatten()
                self.nanome_mesh.triangles = np.asarray(self.computed_triangles).flatten()

            self._plugin.color_by_scheme()
            self.nanome_mesh.upload()

    def change_color_scheme(self, dropdown, item):
        new_color_scheme = self.get_color_scheme()
        if self.color_by != new_color_scheme:
            self.color_by = new_color_scheme
            self._plugin.color_by_scheme(new_color_scheme)
            if self.nanome_mesh is not None:
                self.nanome_mesh.upload()

    def get_color_scheme(self):
        item = next(item for item in self.dd_color_scheme.items if item.selected)
        if item.name == "Element":
            color_scheme = enums.ColorScheme.Element
        elif item.name == "Bfactor":
            color_scheme = enums.ColorScheme.BFactor
        elif item.name == "Chain":
            color_scheme = enums.ColorScheme.Chain
        return color_scheme

    def set_target_complex(self, dropdown, item):
        self._plugin.update_content(dropdown)
        # for c in self.nanome_workspace.complexes:
        #     if c.name == item.name:
        #         self.nanome_complex = c
        #         return

    def set_selected_file(self, dropdown, item):
        self._Vault_mol_file_to_download = item.name
        print(item.name)

    def set_selected_map_file(self, dropdown, item):
        self._Vault_map_file_to_download = item.name
        print(item.name)

    def load_map_from_vault(self):
        if self._Vault_map_file_to_download is not None:
            tfile = self.get_file_from_vault(
                self._Vault_map_file_to_download)
            self._plugin.map_file = tfile

    def update_isosurface(self, iso):
        self.lbl_iso_value.text_value = str(round(iso.current_value, 3))
        self._plugin.update_content(self.lbl_iso_value)
        if self._plugin._map_data is not None:
            self._plugin.generate_isosurface(iso.current_value)
        Logs.debug("Setting iso-value to", str(round(iso.current_value, 3)))

    def update_limited_view_x(self, slider):
        self.limit_x = slider.current_value
        self.label_limit_x.text_value = "Position.x: " + \
            str(round(self.limit_x, 2))
        self._plugin.update_content(self.label_limit_x)
        self.limited_view_pos = [self.limit_x, self.limit_y, self.limit_z]
        self.update_mesh_limited_view()
        x = str(round(self.limit_x, 2))
        y = str(round(self.limit_y, 2))
        z = str(round(self.limit_z, 2))
        Logs.debug("Setting limited view to (", x, y, z, ")")

    def update_limited_view_y(self, slider):
        self.limit_y = slider.current_value
        self.label_limit_y.text_value = "Position.y: " + \
            str(round(self.limit_y, 2))
        self._plugin.update_content(self.label_limit_y)
        self.limited_view_pos = [self.limit_x, self.limit_y, self.limit_z]
        self.update_mesh_limited_view()
        x = str(round(self.limit_x, 2))
        y = str(round(self.limit_y, 2))
        z = str(round(self.limit_z, 2))
        Logs.debug("Setting limited view to (", x, y, z, ")")

    def update_limited_view_z(self, slider):
        self.limit_z = slider.current_value
        self.label_limit_z.text_value = "Position.z: " + \
            str(round(self.limit_z, 2))
        self._plugin.update_content(self.label_limit_z)
        self.limited_view_pos = [self.limit_x, self.limit_y, self.limit_z]
        self.update_mesh_limited_view()
        x = str(round(self.limit_x, 2))
        y = str(round(self.limit_y, 2))
        z = str(round(self.limit_z, 2))
        Logs.debug("Setting limited view to (", x, y, z, ")")

    def update_limited_view_range(self, slider):
        self.limited_view_range = slider.current_value
        self.lbl_limit_range_value.text_value = str(round(self.limited_view_range, 2))
        self._plugin.update_content(self.lbl_limit_range_value)
        # self._plugin.update_mesh_limited_view()
        Logs.debug("Setting limited view range to",
                   str(round(self.limited_view_range, 2)))

    def update_mesh_limited_view(self):
        if self.current_mesh != [] and self.nanome_mesh is not None:
            vertices, normals, triangles = self._plugin.limit_view(
                self.current_mesh, self.limited_view_pos, self.limited_view_range
            )

            self.computed_vertices = np.array(vertices)
            self.computed_normals = np.array(normals)
            self.computed_triangles = np.array(triangles)

            if self.wireframe_mode:
                self.wire_vertices, self.wire_normals, self.wire_triangles = self.wireframe_mesh()
                self.nanome_mesh.vertices = np.asarray(self.wire_vertices).flatten()
                self.nanome_mesh.triangles = np.asarray(self.wire_triangles).flatten()
            else:
                self.nanome_mesh.vertices = np.asarray(self.computed_vertices).flatten()
                self.nanome_mesh.triangles = np.asarray(self.computed_triangles).flatten()
            self.color_by_scheme()
            self.nanome_mesh.upload()

    def update_opacity(self, alpha):
        opacity = alpha.current_value
        self.lbl_opacity_value.text_value = str(round(opacity, 2))
        self._plugin.update_content(self.lbl_opacity_value)
        Logs.debug(f"Setting opacity to {opacity}")
        if self._plugin._map_data is not None and self.nanome_mesh and self.shown:
            self.nanome_mesh.color.a = int(opacity * 255)
            self.nanome_mesh.upload()
