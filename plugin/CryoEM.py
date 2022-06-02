import tempfile

import matplotlib.pyplot as plt
import mcubes
import mrcfile
import nanome
import numpy as np
import pyfqmr
import requests
from nanome.api import structure
from nanome.api.shapes import Mesh, Shape
from nanome.api.ui import Menu
from nanome.util import Color, Logs, Vector3, enums


class CryoEM(nanome.PluginInstance):
    def start(self):
        self.nanome_workspace = None

        self.map_file = None
        self._map_data = None
        self.nanome_mesh = None
        self.iso_value = 0.3
        self.opacity = 0.6
        self._slider_iso = None
        self._slider_opacity = None
        self.limit_x = 0.0
        self.limit_y = 0.0
        self.limit_z = 0.0
        self.limited_view_pos = [0, 0, 0]
        self.limited_view_range = 15.0
        self.current_mesh = []

        self.create_menu()
        self.request_workspace(self.remove_existing_plugin_structure)

    def remove_existing_plugin_structure(self, workspace):
        self.nanome_workspace = workspace
        # First remove previous cryo-em plugin complexes
        if self.nanome_workspace is not None:
            self.nanome_workspace.complexes[:] = [
                c
                for c in self.nanome_workspace.complexes
                if not "CryoEM_plugin" in c.name
            ]

        self.update_workspace(self.nanome_workspace)

    def create_menu(self):
        self.menu = Menu()
        self.menu.title = "Cryo-EM"
        self.menu.width = 0.7
        self.menu.height = 1

        node_image = self.menu.root.create_child_node()
        self.histo_image = node_image.add_new_image()
        node_image.set_size_ratio(0.2)

        node_input = self.menu.root.create_child_node()
        text_input = node_input.add_new_text_input("PDBId")
        # text_input.input_text = "7efc"
        text_input.input_text = "6cl7"
        node_input.set_size_ratio(0.05)

        node_label = self.menu.root.create_child_node()
        self.label_iso = node_label.add_new_label(
            "Iso-value: " + str(round(self.iso_value, 3))
        )
        node_label.set_size_ratio(0.05)

        node_iso = self.menu.root.create_child_node()
        self._slider_iso = node_iso.add_new_slider(-5.0, 5.0, self.iso_value)
        node_iso.set_size_ratio(0.05)

        node_label_opac = self.menu.root.create_child_node()
        self.label_opac = node_label_opac.add_new_label(
            "Opacity: " + str(round(self.opacity, 2))
        )
        node_label_opac.set_size_ratio(0.01)

        opac_node = self.menu.root.create_child_node()
        self._slider_opacity = opac_node.add_new_slider(
            0.01, 1.0, self.opacity)
        opac_node.set_size_ratio(0.05)

        node_label_limit_x = self.menu.root.create_child_node()
        self.label_limit_x = node_label_limit_x.add_new_label(
            "Position.x: " + str(round(self.limit_x, 2))
        )
        node_label_limit_x.set_size_ratio(0.01)

        limit_x_node = self.menu.root.create_child_node()
        self._slider_limit_x = limit_x_node.add_new_slider(
            -50, 50, self.limit_x)
        limit_x_node.set_size_ratio(0.05)

        node_label_limit_y = self.menu.root.create_child_node()
        self.label_limit_y = node_label_limit_y.add_new_label(
            "Position.y: " + str(round(self.limit_y, 2))
        )
        node_label_limit_y.set_size_ratio(0.01)

        limit_y_node = self.menu.root.create_child_node()
        self._slider_limit_y = limit_y_node.add_new_slider(
            -50, 50, self.limit_y)
        limit_y_node.set_size_ratio(0.05)

        node_label_limit_z = self.menu.root.create_child_node()
        self.label_limit_z = node_label_limit_z.add_new_label(
            "Position.z: " + str(round(self.limit_z, 2))
        )
        node_label_limit_z.set_size_ratio(0.01)

        limit_z_node = self.menu.root.create_child_node()
        self._slider_limit_z = limit_z_node.add_new_slider(
            -50, 50, self.limit_z)
        limit_z_node.set_size_ratio(0.05)

        node_label_limit_range = self.menu.root.create_child_node()
        self.label_limit_range = node_label_limit_range.add_new_label(
            "Size: " + str(round(self.limited_view_range, 2))
        )
        node_label_limit_range.set_size_ratio(0.01)

        limit_range_node = self.menu.root.create_child_node()
        self._slider_limit_range = limit_range_node.add_new_slider(
            0, 150, self.limited_view_range
        )
        limit_range_node.set_size_ratio(0.05)

        def download_PDB(textinput):
            pdbid = textinput.input_text
            base = "https://files.rcsb.org/download/"
            self.pdbid = pdbid
            full_url = base + pdbid + ".pdb.gz"
            self.send_notification(
                nanome.util.enums.NotificationTypes.message, "Downloading PDB"
            )
            Logs.message("Downloading PDB file from", full_url)
            response = requests.get(full_url)
            if response.status_code != 200:
                Logs.error("Something went wrong fetching the PDB file")
                self.send_notification(
                    nanome.util.enums.NotificationTypes.error, "Wrong PDB ID"
                )
                return False
            pdb_tempfile = tempfile.NamedTemporaryFile(
                delete=False, prefix="CryoEM_plugin_" + pdbid, suffix=".pdb.gz"
            )
            open(pdb_tempfile.name, "wb").write(response.content)
            pdb_path = pdb_tempfile.name.replace("\\", "/")
            self.send_files_to_load(pdb_path, download_CryoEM_map)
            return True

        def download_CryoEM_map(file):
            Logs.message("Downloading PDB info for ID:", self.pdbid)
            self.send_notification(
                nanome.util.enums.NotificationTypes.message, "Downloading EM data"
            )
            base = "https://data.rcsb.org/rest/v1/core/entry/"
            rest_url = base + self.pdbid
            response = requests.get(rest_url)
            if response.status_code != 200:
                Logs.error("Something went wrong fetching the EM data")
                self.send_notification(
                    nanome.util.enums.NotificationTypes.error,
                    "No EMDB data for" + str(self.pdbid),
                )
                return
            result = response.json()
            k1 = "rcsb_entry_container_identifiers"
            k2 = "emdb_ids"
            if not k1 in result or not k2 in result[k1]:
                Logs.error("No EM data found for", self.pdbid)
                self.send_notification(
                    nanome.util.enums.NotificationTypes.error,
                    "No EMDB data for" + str(self.pdbid),
                )
                return
            emdb_ids = result[k1][k2]
            if len(emdb_ids) >= 1:
                first_emdb = emdb_ids[0]
                Logs.message("Downloading EM data for EMDBID:", first_emdb)

                new_url = (
                    "https://files.rcsb.org/pub/emdb/structures/"
                    + first_emdb
                    + "/map/"
                    + first_emdb.lower().replace("-", "_")
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
                    self.map_file = map_tempfile
                    self.load_map()
                    self.generate_histogram()
                    self.request_workspace(
                        self.set_current_complex_generate_surface)
            else:
                Logs.error("No EM data found for", self.pdbid)
                self.send_notification(
                    nanome.util.enums.NotificationTypes.error,
                    "No EMDB data for",
                    self.pdbid,
                )

        text_input.register_submitted_callback(download_PDB)
        self._slider_iso.register_released_callback(self.update_isosurface)
        self._slider_opacity.register_released_callback(self.update_opacity)
        self._slider_limit_x.register_released_callback(
            self.update_limited_view_x)
        self._slider_limit_y.register_released_callback(
            self.update_limited_view_y)
        self._slider_limit_z.register_released_callback(
            self.update_limited_view_z)
        self._slider_limit_range.register_released_callback(
            self.update_limited_view_range
        )

    def set_current_complex_generate_surface(self, workspace):
        self.nanome_workspace = workspace

        for c in reversed(self.nanome_workspace.complexes):
            if "CryoEM_plugin" in c.name:
                self.nanome_complex = c

        self.set_limited_view_on_cog()
        self.generate_isosurface(self.iso_value)

    def set_limited_view_on_cog(self):
        # Compute center of gravity of structure
        cog = np.array([0.0, 0.0, 0.0])
        count = 0
        for a in self.nanome_complex.atoms:
            count += 1
            cog += np.array([a.position.x, a.position.y, a.position.z])
        cog /= count
        cog -= self._map_origin
        self.limit_x = cog[0]
        self.limit_y = cog[1]
        self.limit_z = cog[2]
        self.limited_view_pos = [self.limit_x, self.limit_y, self.limit_z]
        self._slider_limit_x.current_value = cog[0]
        self._slider_limit_y.current_value = cog[1]
        self._slider_limit_z.current_value = cog[2]
        self.update_content(
            [self._slider_limit_x, self._slider_limit_y, self._slider_limit_z])

    def load_map(self):
        with mrcfile.open(self.map_file.name) as mrc:
            self._map_data = mrc.data
            # mrc.print_header()
            h = mrc.header
            self._map_voxel_size = mrc.voxel_size
            axes_order = np.hstack([h.mapc, h.mapr, h.maps])
            axes_c_order = np.argsort(axes_order)
            transpose_order = np.argsort(axes_order[::-1])
            self._map_data = np.transpose(self._map_data, axes=transpose_order)
            delta = np.diag(np.array(
                [self._map_voxel_size.x, self._map_voxel_size.y, self._map_voxel_size.z]))
            offsets = np.hstack([h.nxstart, h.nystart, h.nzstart])[
                axes_c_order] * np.diag(delta)
            self._map_origin = np.hstack(
                [h.origin.x, h.origin.y, h.origin.z]) + offsets

    def on_run(self):
        self.menu.enabled = True
        self.update_menu(self.menu)

    def update_isosurface(self, iso):
        self.label_iso.text_value = "Iso-value: " + \
            str(round(iso.current_value, 3))
        self.update_content(self.label_iso)
        if self._map_data is not None:
            self.generate_isosurface(iso.current_value)
        Logs.debug("Setting iso-value to", str(round(iso.current_value, 3)))

    def update_limited_view_x(self, slider):
        self.limit_x = slider.current_value
        self.label_limit_x.text_value = "Position.x: " + \
            str(round(self.limit_x, 2))
        self.update_content(self.label_limit_x)
        self.limited_view_pos = [self.limit_x, self.limit_y, self.limit_z]
        self.update_mesh_limited_view()
        Logs.debug("Setting limited view to (", str(round(self.limit_x, 2)), str(
            round(self.limit_y, 2)), str(round(self.limit_z, 2)), ")")

    def update_limited_view_y(self, slider):
        self.limit_y = slider.current_value
        self.label_limit_y.text_value = "Position.y: " + \
            str(round(self.limit_y, 2))
        self.update_content(self.label_limit_y)
        self.limited_view_pos = [self.limit_x, self.limit_y, self.limit_z]
        self.update_mesh_limited_view()
        Logs.debug("Setting limited view to (", str(round(self.limit_x, 2)), str(
            round(self.limit_y, 2)), str(round(self.limit_z, 2)), ")")

    def update_limited_view_z(self, slider):
        self.limit_z = slider.current_value
        self.label_limit_z.text_value = "Position.z: " + \
            str(round(self.limit_z, 2))
        self.update_content(self.label_limit_z)
        self.limited_view_pos = [self.limit_x, self.limit_y, self.limit_z]
        self.update_mesh_limited_view()
        Logs.debug("Setting limited view to (", str(round(self.limit_x, 2)), str(
            round(self.limit_y, 2)), str(round(self.limit_z, 2), ")"))

    def update_limited_view_range(self, slider):
        self.limited_view_range = slider.current_value
        self.label_limit_range.text_value = "Size: " + str(
            round(self.limited_view_range, 2)
        )
        self.update_content(self.label_limit_range)
        self.update_mesh_limited_view()
        Logs.debug("Setting limited view range to",
                   str(round(self.limited_view_range, 2)))

    def update_mesh_limited_view(self):
        if self.current_mesh != [] and self.nanome_mesh is not None:
            vertices, normals, triangles = self.limit_view(
                self.current_mesh, self.limited_view_pos, self.limited_view_range
            )

            self.nanome_mesh.vertices = np.asarray(vertices).flatten()
            # self.nanome_mesh.normals = np.asarray(normals).flatten()
            self.nanome_mesh.triangles = np.asarray(triangles).flatten()

            self.nanome_mesh.upload()

    def update_opacity(self, alpha):

        self.opacity = alpha.current_value
        self.label_opac.text_value = "Opacity: " + str(round(self.opacity, 2))
        self.update_content(self.label_opac)

        if self._map_data is not None and self.nanome_mesh:
            self.nanome_mesh.color.a = int(self.opacity * 255)
            self.nanome_mesh.upload()
            Logs.debug("Setting opacity to", int(self.opacity * 255))

    def limit_view(self, mesh, position, range):
        if range <= 0:
            return mesh
        vertices, normals, triangles = mesh

        pos = np.asarray(position)
        idv = 0
        to_keep = []
        for v in vertices:
            vert = np.asarray(v)
            dist = np.linalg.norm(vert - pos)
            if dist <= range:
                to_keep.append(idv)
            idv += 1
        if len(to_keep) == len(vertices):
            return mesh

        new_vertices = []
        new_triangles = []
        new_normals = []
        mapping = np.full(len(vertices), -1, np.int32)
        idv = 0
        for i in to_keep:
            mapping[i] = idv
            new_vertices.append(vertices[i])
            new_normals.append(normals[i])
            idv += 1

        for t in triangles:
            if mapping[t[0]] != -1 and mapping[t[1]] != -1 and mapping[t[2]] != -1:
                new_triangles.append(
                    [mapping[t[0]], mapping[t[1]], mapping[t[2]]])

        return (
            np.asarray(new_vertices),
            np.asarray(new_normals),
            np.asarray(new_triangles),
        )

    def generate_isosurface(self, iso, decimation_factor=5):
        Logs.message("Generating iso-surface for iso-value " +
                     str(round(iso, 3)))
        self.iso_value = iso

        self.set_plugin_list_button(
            enums.PluginListButtonType.run, "Running...", False)

        # Compute iso-surface with marching cubes algorithm
        vertices, triangles = mcubes.marching_cubes(self._map_data, iso)

        target = max(100, len(triangles) / decimation_factor)

        mesh_simplifier = pyfqmr.Simplify()
        mesh_simplifier.setMesh(np.asarray(vertices), np.asarray(triangles))
        mesh_simplifier.simplify_mesh(
            target_count=target, aggressiveness=7, preserve_border=True, verbose=0
        )

        vertices, triangles, normals = mesh_simplifier.getMesh()

        if self._map_voxel_size.x > 0.0001:
            voxel_size = np.array(
                [self._map_voxel_size.x, self._map_voxel_size.y, self._map_voxel_size.z]
            )
            vertices *= voxel_size

        self.current_mesh = [vertices, normals, triangles]

        vertices, normals, triangles = self.limit_view(
            (vertices, normals, triangles),
            self.limited_view_pos,
            self.limited_view_range,
        )

        if self.nanome_mesh is None:
            self.nanome_mesh = Mesh()


        self.nanome_mesh.vertices = np.asarray(vertices).flatten()
        # self.nanome_mesh.normals = np.asarray(normals).flatten()
        self.nanome_mesh.triangles = np.asarray(triangles).flatten()

        self.nanome_mesh.anchors[0].anchor_type = nanome.util.enums.ShapeAnchorType.Workspace

        self.nanome_mesh.color = Color(128, 128, 255, int(self.opacity * 255))

        anchor = self.nanome_mesh.anchors[0]
        anchor.anchor_type = nanome.util.enums.ShapeAnchorType.Complex
        anchor.target = self.nanome_complex.index

        anchor.local_offset = Vector3(
            self._map_origin[0], self._map_origin[1], self._map_origin[2])

        Logs.message(
            "Uploading iso-surface ("
            + str(len(self.nanome_mesh.vertices))
            + " vertices)"
        )
        self.nanome_mesh.upload(self.done_updating)

    def generate_histogram(self):
        flat = self._map_data.flatten()
        plt.hist(flat, bins=100)
        plt.title("Iso-value distribution")
        self.png_tempfile = tempfile.NamedTemporaryFile(
            delete=False, suffix=".png")
        plt.savefig(self.png_tempfile.name)
        self.histo_image.file_path = self.png_tempfile.name
        self.update_content(self.histo_image)

    def done_updating(self, m):
        Logs.message(
            "Done updating mesh for iso-value " + str(round(self.iso_value, 3))
        )
        self.set_plugin_list_button(
            enums.PluginListButtonType.run, "Run", True)


def main():
    plugin = nanome.Plugin(
        "Cryo-EM",
        "Nanome plugin to load Cryo-EM maps and display them in Nanome as iso-surfaces",
        "other",
        False,
    )
    plugin.set_plugin_class(CryoEM)
    plugin.run()


if __name__ == "__main__":
    main()
