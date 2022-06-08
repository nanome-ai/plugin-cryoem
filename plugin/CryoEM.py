import tempfile

import matplotlib.pyplot as plt
import mcubes
import mrcfile
import nanome
import numpy as np
import pyfqmr
import randomcolor
import requests
from matplotlib import cm
from nanome.api.shapes import Mesh
from nanome.api.ui import Menu
from nanome.util import Color, Logs, Vector3, enums
from scipy.spatial import KDTree


class CryoEM(nanome.PluginInstance):
    def start(self):
        self.nanome_workspace = None

        self.map_file = None
        self._map_data = None
        self.nanome_mesh = None
        self.nanome_complex = None
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
        self.shown = True
        self.color_by = enums.ColorScheme.BFactor

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

        # node_label_limit_x = self.menu.root.create_child_node()
        # self.label_limit_x = node_label_limit_x.add_new_label(
        #     "Position.x: " + str(round(self.limit_x, 2))
        # )
        # node_label_limit_x.set_size_ratio(0.01)

        # limit_x_node = self.menu.root.create_child_node()
        # self._slider_limit_x = limit_x_node.add_new_slider(
        #     -50, 50, self.limit_x)
        # limit_x_node.set_size_ratio(0.05)

        # node_label_limit_y = self.menu.root.create_child_node()
        # self.label_limit_y = node_label_limit_y.add_new_label(
        #     "Position.y: " + str(round(self.limit_y, 2))
        # )
        # node_label_limit_y.set_size_ratio(0.01)

        # limit_y_node = self.menu.root.create_child_node()
        # self._slider_limit_y = limit_y_node.add_new_slider(
        #     -50, 50, self.limit_y)
        # limit_y_node.set_size_ratio(0.05)

        # node_label_limit_z = self.menu.root.create_child_node()
        # self.label_limit_z = node_label_limit_z.add_new_label(
        #     "Position.z: " + str(round(self.limit_z, 2))
        # )
        # node_label_limit_z.set_size_ratio(0.01)

        # limit_z_node = self.menu.root.create_child_node()
        # self._slider_limit_z = limit_z_node.add_new_slider(
        #     -50, 50, self.limit_z)
        # limit_z_node.set_size_ratio(0.05)

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

        node_color_scheme_label = self.menu.root.create_child_node()
        self.label_color_scheme = node_color_scheme_label.add_new_label(
            "Color scheme: " + str(round(self.limited_view_range, 2))
        )
        node_color_scheme_label.set_size_ratio(0.01)

        color_scheme_node = self.menu.root.create_child_node()
        self._dropdown_color_scheme = color_scheme_node.add_new_dropdown()
        color_scheme_node.set_size_ratio(0.05)
        self._dropdown_color_scheme.items = [nanome.ui.DropdownItem(
            name) for name in ["Bfactor", "Element", "Chain"]]
        self._dropdown_color_scheme.items[0].selected = True
        color_scheme_node.forward_dist = .001

        show_hide_node = self.menu.root.create_child_node()
        self._show_button = show_hide_node.add_new_toggle_switch("Show/Hide")
        self._show_button.selected = True
        show_hide_node.set_size_ratio(0.05)
        show_hide_node.forward_dist = 0.001

        def download_PDB(textinput):
            self.current_mesh = []
            if self.nanome_mesh is not None:
                self.nanome_mesh.destroy()
            self.nanome_mesh = None
            self.nanome_complex = None
            
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

        def show_hide_map(toggle):
            if self.nanome_mesh is not None:
                self.nanome_mesh.color.a = int(
                    self.opacity * 255) if toggle.selected else 0
                self.shown = toggle.selected
                self.nanome_mesh.upload()

        def change_color_scheme(dropdown, item):
            if item.name == "Element":
                new_color_scheme = enums.ColorScheme.Element
            elif item.name == "Bfactor":
                new_color_scheme = enums.ColorScheme.BFactor
            elif item.name == "Chain":
                new_color_scheme = enums.ColorScheme.Chain
            if self.color_by != new_color_scheme:
                self.color_by = new_color_scheme
                self.color_by_scheme()
                if self.nanome_mesh is not None:
                    self.nanome_mesh.upload()

        text_input.register_submitted_callback(download_PDB)
        self._slider_iso.register_released_callback(self.update_isosurface)
        self._slider_opacity.register_released_callback(self.update_opacity)
        # self._slider_limit_x.register_released_callback(
        #     self.update_limited_view_x)
        # self._slider_limit_y.register_released_callback(
        #     self.update_limited_view_y)
        # self._slider_limit_z.register_released_callback(
        #     self.update_limited_view_z)
        self._slider_limit_range.register_released_callback(
            self.update_limited_view_range
        )
        self._dropdown_color_scheme.register_item_clicked_callback(
            change_color_scheme)
        self._show_button.register_pressed_callback(show_hide_map)

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
        # self._slider_limit_x.current_value = cog[0]
        # self._slider_limit_y.current_value = cog[1]
        # self._slider_limit_z.current_value = cog[2]
        # self.update_content(
        # [self._slider_limit_x, self._slider_limit_y, self._slider_limit_z])

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
        x = str(round(self.limit_x, 2))
        y = str(round(self.limit_y, 2))
        z = str(round(self.limit_z, 2))
        Logs.debug("Setting limited view to (", x, y, z, ")")

    def update_limited_view_y(self, slider):
        self.limit_y = slider.current_value
        self.label_limit_y.text_value = "Position.y: " + \
            str(round(self.limit_y, 2))
        self.update_content(self.label_limit_y)
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
        self.update_content(self.label_limit_z)
        self.limited_view_pos = [self.limit_x, self.limit_y, self.limit_z]
        self.update_mesh_limited_view()
        x = str(round(self.limit_x, 2))
        y = str(round(self.limit_y, 2))
        z = str(round(self.limit_z, 2))
        Logs.debug("Setting limited view to (", x, y, z, ")")

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

            self.computed_vertices = np.array(vertices)
            self.nanome_mesh.vertices = np.asarray(vertices).flatten()
            # self.nanome_mesh.normals = np.asarray(normals).flatten()
            self.nanome_mesh.triangles = np.asarray(triangles).flatten()

            self.color_by_scheme()

            self.nanome_mesh.upload()

    def update_opacity(self, alpha):

        self.opacity = alpha.current_value
        self.label_opac.text_value = "Opacity: " + str(round(self.opacity, 2))
        self.update_content(self.label_opac)

        if self._map_data is not None and self.nanome_mesh and self.shown:
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

        self.computed_vertices = np.array(vertices)
        self.nanome_mesh.vertices = np.asarray(vertices).flatten()
        # self.nanome_mesh.normals = np.asarray(normals).flatten()
        self.nanome_mesh.triangles = np.asarray(triangles).flatten()

        self.nanome_mesh.anchors[0].anchor_type = nanome.util.enums.ShapeAnchorType.Workspace

        # self.nanome_mesh.color = Color(128, 128, 255, int(self.opacity * 255))
        self.nanome_mesh.color = Color(255, 255, 255, int(self.opacity * 255))

        if not self.shown:
            self.nanome_mesh.color.a = 0

        anchor = self.nanome_mesh.anchors[0]
        anchor.anchor_type = nanome.util.enums.ShapeAnchorType.Complex
        anchor.target = self.nanome_complex.index

        anchor.local_offset = Vector3(
            self._map_origin[0], self._map_origin[1], self._map_origin[2])

        self.color_by_scheme()

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

    def color_by_scheme(self):
        if self.nanome_mesh is None:
            return
        if self.color_by == enums.ColorScheme.Element:
            self.color_by_element()
        elif self.color_by == enums.ColorScheme.BFactor:
            self.color_by_bfactor()
        elif self.color_by == enums.ColorScheme.Chain:
            self.color_by_chain()

    def color_by_element(self):
        atom_positions = []
        atoms = []
        for a in self.nanome_complex.atoms:
            atoms.append(a)
            p = a.position
            atom_positions.append(np.array([p.x, p.y, p.z]))
        kdtree = KDTree(np.array(atom_positions))
        result, indices = kdtree.query(
            self.computed_vertices+self._map_origin, distance_upper_bound=20)
        colors = []
        for i in indices:
            if i >= 0 and i < len(atom_positions):
                colors += cpk_colors(atoms[i])
            else:
                colors += [0.0, 0.0, 0.0, 1.0]
        self.nanome_mesh.colors = np.array(colors)

    def color_by_chain(self):
        molecule = self.nanome_complex._molecules[self.nanome_complex.current_frame]
        n_chain = len(list(molecule.chains))

        rdcolor = randomcolor.RandomColor(seed=1234)
        chain_cols = rdcolor.generate(format_="rgb", count=n_chain)

        id_chain = 0
        color_per_atom = []
        for c in molecule.chains:
            col = chain_cols[id_chain]
            col = col.replace("rgb(", "").replace(
                ")", "").replace(",", "").split()
            chain_color = [int(i) / 255.0 for i in col] + [1.0]
            id_chain += 1
            for atom in c.atoms:
                color_per_atom.append(chain_color)

        colors = []

        # No need for neighbor search as all vertices have the same color
        if n_chain == 1:
            for i in range(len(self.computed_vertices)):
                colors += color_per_atom[0]
            self.nanome_mesh.colors = np.array(colors)
            return

        atom_positions = []
        atoms = []
        for a in self.nanome_complex.atoms:
            atoms.append(a)
            p = a.position
            atom_positions.append(np.array([p.x, p.y, p.z]))

        # Create a KDTree for fast neighbor search
        # Look for the closest atom near each vertex
        kdtree = KDTree(np.array(atom_positions))
        result, indices = kdtree.query(
            self.computed_vertices+self._map_origin, distance_upper_bound=20)
        for i in indices:
            if i >= 0 and i < len(atom_positions):
                colors += color_per_atom[i]
            else:
                colors += [0.0, 0.0, 0.0, 1.0]
        self.nanome_mesh.colors = np.array(colors)

    def color_by_bfactor(self):

        sections = 128
        cm_subsection = np.linspace(0.0, 1.0, sections)
        colors_rainbow = [cm.jet(x) for x in cm_subsection]

        atom_positions = []
        atoms = []
        for a in self.nanome_complex.atoms:
            atoms.append(a)
            p = a.position
            atom_positions.append(np.array([p.x, p.y, p.z]))

        # Create a KDTree for fast neighbor search
        # Look for the closest atom near each vertex
        kdtree = KDTree(np.array(atom_positions))
        result, indices = kdtree.query(
            self.computed_vertices+self._map_origin, distance_upper_bound=20)

        colors = []
        bfactors = np.array([a.bfactor for a in atoms])
        minbf = np.min(bfactors)
        maxbf = np.max(bfactors)
        if np.abs(maxbf - minbf) < 0.001:
            maxbf = minbf + 1.0

        for i in indices:
            if i >= 0 and i < len(atom_positions):
                bf = bfactors[i]
                norm_bf = (bf - minbf) / (maxbf - minbf)
                id_color = int(norm_bf * (sections-1))
                colors += colors_rainbow[int(id_color)]
            else:
                colors += [0.0, 0.0, 0.0, 1.0]
        self.nanome_mesh.colors = np.array(colors)


def chain_color(id_chain):
    molecule = self._complex._molecules[self._complex.current_frame]
    n_chain = len(list(molecule.chains))

    rdcolor = randomcolor.RandomColor(seed=1234)
    chain_cols = rdcolor.generate(format_="rgb", count=n_chain)

    id_chain = 0
    color_per_atom = []
    for c in molecule.chains:
        col = chain_cols[id_chain]
        col = col.replace("rgb(", "").replace(")", "").replace(",", "").split()
        chain_color = [int(i) / 255.0 for i in col] + [1.0]
        id_chain += 1
        for atom in c.atoms:
            color_per_atom.append(chain_color)

    colors = []
    for idx in self._temp_mesh["indices"]:
        colors.append(color_per_atom[idx])
    return np.array(colors)


def cpk_colors(a):
    colors = {}
    colors["xx"] = "#030303"
    colors["h"] = "#FFFFFF"
    colors["he"] = "#D9FFFF"
    colors["li"] = "#CC80FF"
    colors["be"] = "#C2FF00"
    colors["b"] = "#FFB5B5"
    colors["c"] = "#909090"
    colors["n"] = "#3050F8"
    colors["o"] = "#FF0D0D"
    colors["f"] = "#B5FFFF"
    colors["ne"] = "#B3E3F5"
    colors["na"] = "#AB5CF2"
    colors["mg"] = "#8AFF00"
    colors["al"] = "#BFA6A6"
    colors["si"] = "#F0C8A0"
    colors["p"] = "#FF8000"
    colors["s"] = "#FFFF30"
    colors["cl"] = "#1FF01F"
    colors["ar"] = "#80D1E3"
    colors["k"] = "#8F40D4"
    colors["ca"] = "#3DFF00"
    colors["sc"] = "#E6E6E6"
    colors["ti"] = "#BFC2C7"
    colors["v"] = "#A6A6AB"
    colors["cr"] = "#8A99C7"
    colors["mn"] = "#9C7AC7"
    colors["fe"] = "#E06633"
    colors["co"] = "#F090A0"
    colors["ni"] = "#50D050"
    colors["cu"] = "#C88033"
    colors["zn"] = "#7D80B0"
    colors["ga"] = "#C28F8F"
    colors["ge"] = "#668F8F"
    colors["as"] = "#BD80E3"
    colors["se"] = "#FFA100"
    colors["br"] = "#A62929"
    colors["kr"] = "#5CB8D1"
    colors["rb"] = "#702EB0"
    colors["sr"] = "#00FF00"
    colors["y"] = "#94FFFF"
    colors["zr"] = "#94E0E0"
    colors["nb"] = "#73C2C9"
    colors["mo"] = "#54B5B5"
    colors["tc"] = "#3B9E9E"
    colors["ru"] = "#248F8F"
    colors["rh"] = "#0A7D8C"
    colors["pd"] = "#006985"
    colors["ag"] = "#C0C0C0"
    colors["cd"] = "#FFD98F"
    colors["in"] = "#A67573"
    colors["sn"] = "#668080"
    colors["sb"] = "#9E63B5"
    colors["te"] = "#D47A00"
    colors["i"] = "#940094"
    colors["xe"] = "#429EB0"
    colors["cs"] = "#57178F"
    colors["ba"] = "#00C900"
    colors["la"] = "#70D4FF"
    colors["ce"] = "#FFFFC7"
    colors["pr"] = "#D9FFC7"
    colors["nd"] = "#C7FFC7"
    colors["pm"] = "#A3FFC7"
    colors["sm"] = "#8FFFC7"
    colors["eu"] = "#61FFC7"
    colors["gd"] = "#45FFC7"
    colors["tb"] = "#30FFC7"
    colors["dy"] = "#1FFFC7"
    colors["ho"] = "#00FF9C"
    colors["er"] = "#00E675"
    colors["tm"] = "#00D452"
    colors["yb"] = "#00BF38"
    colors["lu"] = "#00AB24"
    colors["hf"] = "#4DC2FF"
    colors["ta"] = "#4DA6FF"
    colors["w"] = "#2194D6"
    colors["re"] = "#267DAB"
    colors["os"] = "#266696"
    colors["ir"] = "#175487"
    colors["pt"] = "#D0D0E0"
    colors["au"] = "#FFD123"
    colors["hg"] = "#B8B8D0"
    colors["tl"] = "#A6544D"
    colors["pb"] = "#575961"
    colors["bi"] = "#9E4FB5"
    colors["po"] = "#AB5C00"
    colors["at"] = "#754F45"
    colors["rn"] = "#428296"
    colors["fr"] = "#420066"
    colors["ra"] = "#007D00"
    colors["ac"] = "#70ABFA"
    colors["th"] = "#00BAFF"
    colors["pa"] = "#00A1FF"
    colors["u"] = "#008FFF"
    colors["np"] = "#0080FF"
    colors["pu"] = "#006BFF"
    colors["am"] = "#545CF2"
    colors["cm"] = "#785CE3"
    colors["bk"] = "#8A4FE3"
    colors["cf"] = "#A136D4"
    colors["es"] = "#B31FD4"
    colors["fm"] = "#B31FBA"
    colors["md"] = "#B30DA6"
    colors["no"] = "#BD0D87"
    colors["lr"] = "#C70066"
    colors["rf"] = "#CC0059"
    colors["db"] = "#D1004F"
    colors["sg"] = "#D90045"
    colors["bh"] = "#E00038"
    colors["hs"] = "#E6002E"
    colors["mt"] = "#EB0026"
    colors["ds"] = "#ED0023"
    colors["rg"] = "#F00021"
    colors["cn"] = "#E5001E"
    colors["nh"] = "#F4001C"
    colors["fl"] = "#F70019"
    colors["mc"] = "#FA0019"
    colors["lv"] = "#FC0017"
    colors["ts"] = "#FC0014"
    colors["og"] = "#FC000F"
    a_type = a.symbol.lower()
    if a_type not in colors:
        return [1.0, 0, 1.0, 1.0]  # Pink unknown
    h = colors[a_type].lstrip('#')
    return list(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)) + [1.0]


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
