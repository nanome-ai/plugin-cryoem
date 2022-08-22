import os
import tempfile

import matplotlib.pyplot as plt
import mcubes
import mrcfile
import nanome
import numpy as np
import pyfqmr
import randomcolor
from matplotlib import cm
from nanome.api.shapes import Mesh
from nanome.util import Color, Logs, Vector3, async_callback, enums
from scipy.spatial import KDTree

from .VaultManager import VaultManager
from .menu import MainMenu


API_KEY = os.environ.get('API_KEY', None)
SERVER_URL = os.environ.get('SERVER_URL', None)


class CryoEM(nanome.AsyncPluginInstance):

    @async_callback
    async def start(self):
        # self.set_plugin_list_button(
        #     enums.PluginListButtonType.run, "Creating Menu...", False)
        # await self.get_vault_file_list()
        self.nanome_workspace = None

        self._Vault_mol_file_to_download = None
        self._Vault_map_file_to_download = None
        self.map_file = None
        self._map_data = None
        self.nanome_mesh = None
        self.nanome_complex = None
        self.iso_value = 0.0
        self.opacity = 0.6
        self._slider_iso = None
        self._slider_opacity = None
        self.limit_x = 0.0
        self.limit_y = 0.0
        self.limit_z = 0.0
        self.map_prefered_level = 0.0
        self.limited_view_pos = [0, 0, 0]
        self.limited_view_range = 15.0
        self.current_mesh = []
        self.shown = True
        self.wireframe_mode = False
        self.color_by = enums.ColorScheme.BFactor
        # ws = await self.request_workspace()
        self.menu = MainMenu(self)
        self.set_plugin_list_button(
            enums.PluginListButtonType.run, "Run", True)

    def on_run(self):
        self.menu.enable()

    async def get_vault_file_list(self):
        self._vault_manager = VaultManager(API_KEY, SERVER_URL)
        presenter_info = await self.request_presenter_info()
        self._user_id = presenter_info.account_id

        self.user_files = []
        user_folder = self._vault_manager.list_path(self._user_id)
        if not "files" in user_folder:
            Logs.error("Failed to get Vault files")
            return
        self.user_files = user_folder['files']

    def get_file_from_vault(self, filename):
        name, ext = os.path.splitext(filename)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        file_path = os.path.join(self._user_id, filename)
        self._vault_manager.get_file(file_path, None, temp_file.path)
        return temp_file.name

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

    def set_current_complex_generate_surface(self, workspace):
        self.nanome_workspace = workspace
        self.nanome_complex = None

        for c in reversed(self.nanome_workspace.complexes):
            if "CryoEM_plugin" in c.name:
                self.nanome_complex = c

        self.set_limited_view_on_cog()
        self.generate_isosurface(self.iso_value)

    def set_limited_view_on_cog(self):
        # Compute center of gravity of structure
        cog = np.array([0.0, 0.0, 0.0])
        if self.nanome_complex is None:
            self.limit_x = cog[0]
            self.limit_y = cog[1]
            self.limit_z = cog[2]
            self.limited_view_pos = [self.limit_x, self.limit_y, self.limit_z]
            return
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

            self.iso_value = self.map_prefered_level
            self._slider_iso.current_value = self.iso_value
            self.label_iso.text_value = "Iso-value: " + \
                str(round(self.iso_value, 3))
            self.update_content(self.label_iso)
            self.update_content(self._slider_iso)

    def generate_isosurface(self, iso, decimation_factor=5):
        Logs.message("Generating iso-surface for iso-value " +
                     str(round(iso, 3)))
        self.iso_value = iso

        self.set_plugin_list_button(
            enums.PluginListButtonType.run, "Running...", False)

        # Compute iso-surface with marching cubes algorithm
        vertices, triangles = mcubes.marching_cubes(self._map_data, iso)

        Logs.debug("Decimating mesh")
        target = max(1000, len(triangles) / decimation_factor)

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
        self.computed_normals = np.array(normals)
        self.computed_triangles = np.array(triangles)

        self.nanome_mesh.vertices = np.asarray(self.computed_vertices).flatten()
        # self.nanome_mesh.normals = np.asarray(self.computed_normals).flatten()
        self.nanome_mesh.triangles = np.asarray(self.computed_triangles).flatten()

        anchor = self.nanome_mesh.anchors[0]

        anchor.anchor_type = nanome.util.enums.ShapeAnchorType.Workspace
        anchor.local_offset = Vector3(
            self._map_origin[0], self._map_origin[1], self._map_origin[2])

        self.nanome_mesh.color = Color(255, 255, 255, int(self.opacity * 255))

        if not self.shown:
            self.nanome_mesh.color.a = 0

        if self.nanome_complex is not None:
            anchor.anchor_type = nanome.util.enums.ShapeAnchorType.Complex
            anchor.target = self.nanome_complex.index

        if self.wireframe_mode:
            self.wire_vertices, self.wire_normals, self.wire_triangles = self.wireframe_mesh()
            self.nanome_mesh.vertices = np.asarray(self.wire_vertices).flatten()
            self.nanome_mesh.triangles = np.asarray(self.wire_triangles).flatten()
        self.color_by_scheme()

        Logs.message(
            "Uploading iso-surface ("
            + str(len(self.nanome_mesh.vertices))
            + " vertices)"
        )
        self.nanome_mesh.upload(self.done_updating)

    def generate_histogram(self):
        flat = self._map_data.flatten()
        minmap = np.min(flat)
        flat_offset = flat + abs(minmap) + 0.001
        hist, bins = np.histogram(flat_offset, bins=1000)
        logbins = np.logspace(np.log10(bins[0]), np.log10(bins[-1]), len(bins))

        plt.hist(flat, bins=logbins - abs(minmap))
        plt.ylim(bottom=10)
        plt.yscale('log')
        plt.title("Level histogram")
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
        if self.nanome_complex is None:
            return

        verts = self.computed_vertices if not self.wireframe_mode else self.wire_vertices

        if len(verts) < 3:
            return

        atom_positions = []
        atoms = []
        for a in self.nanome_complex.atoms:
            atoms.append(a)
            p = a.position
            atom_positions.append(np.array([p.x, p.y, p.z]))
        kdtree = KDTree(np.array(atom_positions))
        result, indices = kdtree.query(
            verts + self._map_origin, distance_upper_bound=20)
        colors = []
        for i in indices:
            if i >= 0 and i < len(atom_positions):
                colors += cpk_colors(atoms[i])
            else:
                colors += [0.0, 0.0, 0.0, 1.0]
        self.nanome_mesh.colors = np.array(colors)

    def color_by_chain(self):
        if self.nanome_complex is None:
            return
        verts = self.computed_vertices if not self.wireframe_mode else self.wire_vertices
        if len(verts) < 3:
            return

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
            for i in range(len(verts)):
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
            verts + self._map_origin, distance_upper_bound=20)
        for i in indices:
            if i >= 0 and i < len(atom_positions):
                colors += color_per_atom[i]
            else:
                colors += [0.0, 0.0, 0.0, 1.0]
        self.nanome_mesh.colors = np.array(colors)

    def color_by_bfactor(self):
        if self.nanome_complex is None:
            return
        verts = self.computed_vertices if not self.wireframe_mode else self.wire_vertices
        if len(verts) < 3:
            return

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
            verts + self._map_origin, distance_upper_bound=20)

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
                id_color = int(norm_bf * (sections - 1))
                colors += colors_rainbow[int(id_color)]
            else:
                colors += [0.0, 0.0, 0.0, 1.0]
        self.nanome_mesh.colors = np.array(colors)

    def wireframe_mesh(self, wiresize=0.01):
        ntri = len(self.computed_triangles) * 3

        new_verts = np.zeros((ntri * 4, 3))
        new_tris = np.zeros((ntri * 4, 3), dtype=np.int32)
        new_norms = np.zeros((ntri * 4, 3))
        # new_cols = np.zeros((ntri * 4, 3))

        for i in range(int(ntri / 3)):
            t1 = self.computed_triangles[i][0]
            t2 = self.computed_triangles[i][1]
            t3 = self.computed_triangles[i][2]

            if t1 == t2 or t2 == t3 or t1 == t3:
                continue

            v1 = np.array(self.computed_vertices[t1])
            v2 = np.array(self.computed_vertices[t2])
            v3 = np.array(self.computed_vertices[t3])

            n1 = np.array(self.computed_normals[t1])
            n2 = np.array(self.computed_normals[t2])
            n3 = np.array(self.computed_normals[t3])

            v1v2 = v2 - v1
            v2v3 = v3 - v2
            v3v1 = v1 - v3

            sidev1 = np.linalg.norm(np.cross(v1v2, n1))
            sidev2 = np.linalg.norm(np.cross(v2v3, n2))
            sidev3 = np.linalg.norm(np.cross(v3v1, n3))

            newId = i * 3 * 4
            newIdT = i * 6 * 2

            new_verts[newId + 0] = v1 + sidev1 * wiresize
            new_verts[newId + 1] = v1 - sidev1 * wiresize
            new_verts[newId + 2] = v2 + sidev1 * wiresize
            new_verts[newId + 3] = v2 - sidev1 * wiresize

            new_verts[newId + 4] = v2 + sidev2 * wiresize
            new_verts[newId + 5] = v2 - sidev2 * wiresize
            new_verts[newId + 6] = v3 + sidev2 * wiresize
            new_verts[newId + 7] = v3 - sidev2 * wiresize

            new_verts[newId + 8] = v3 + sidev3 * wiresize
            new_verts[newId + 9] = v3 - sidev3 * wiresize
            new_verts[newId + 10] = v1 + sidev3 * wiresize
            new_verts[newId + 11] = v1 - sidev3 * wiresize

            new_norms[newId + 0] = n1
            # new_cols[newId + 0] = cols[t1]
            new_norms[newId + 1] = n1
            # new_cols[newId + 1] = cols[t1]
            new_norms[newId + 2] = n2
            # new_cols[newId + 2] = cols[t2]
            new_norms[newId + 3] = n2
            # new_cols[newId + 3] = cols[t2]

            new_norms[newId + 4] = n2
            # new_cols[newId + 4] = cols[t2]
            new_norms[newId + 5] = n2
            # new_cols[newId + 5] = cols[t2]
            new_norms[newId + 6] = n3
            # new_cols[newId + 6] = cols[t3]
            new_norms[newId + 7] = n3
            # new_cols[newId + 7] = cols[t3]

            new_norms[newId + 8] = n3
            # new_cols[newId + 8] = cols[t3]
            new_norms[newId + 9] = n3
            # new_cols[newId + 9] = cols[t3]
            new_norms[newId + 10] = n1
            # new_cols[newId + 10] = cols[t1]
            new_norms[newId + 11] = n1
            # new_cols[newId + 11] = cols[t1]

            new_tris[newIdT][0] = newId
            new_tris[newIdT + 6] = newId + 1
            new_tris[newIdT][1] = newId + 1
            new_tris[newIdT + 6] = newId + 0
            new_tris[newIdT][2] = newId + 2
            new_tris[newIdT + 6] = newId + 2

            new_tris[newIdT + 1][0] = newId + 1
            new_tris[newIdT + 7] = newId + 3
            new_tris[newIdT + 1][1] = newId + 3
            new_tris[newIdT + 7] = newId + 1
            new_tris[newIdT + 1][2] = newId + 2
            new_tris[newIdT + 7] = newId + 2

            new_tris[newIdT + 2][0] = newId + 4
            new_tris[newIdT + 8][0] = newId + 5
            new_tris[newIdT + 2][1] = newId + 5
            new_tris[newIdT + 8][1] = newId + 4
            new_tris[newIdT + 2][2] = newId + 6
            new_tris[newIdT + 8][2] = newId + 6

            new_tris[newIdT + 3][0] = newId + 5
            new_tris[newIdT + 9][0] = newId + 7
            new_tris[newIdT + 3][1] = newId + 7
            new_tris[newIdT + 9][1] = newId + 5
            new_tris[newIdT + 3][2] = newId + 6
            new_tris[newIdT + 9][2] = newId + 6

            new_tris[newIdT + 4][0] = newId + 8
            new_tris[newIdT + 10][0] = newId + 9
            new_tris[newIdT + 4][1] = newId + 9
            new_tris[newIdT + 10][1] = newId + 8
            new_tris[newIdT + 4][2] = newId + 10
            new_tris[newIdT + 10][2] = newId + 10

            new_tris[newIdT + 5][0] = newId + 9
            new_tris[newIdT + 11][0] = newId + 11
            new_tris[newIdT + 5][1] = newId + 11
            new_tris[newIdT + 11][1] = newId + 9
            new_tris[newIdT + 5][2] = newId + 10
            new_tris[newIdT + 11][2] = newId + 10
        return (new_verts, new_norms, new_tris)


def chain_color(self, id_chain):
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
