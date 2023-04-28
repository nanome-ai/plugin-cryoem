import gzip
import matplotlib.pyplot as plt
import mcubes
import numpy as np
import os
import pyfqmr
import randomcolor
import tempfile
import time
from iotbx.data_manager import DataManager
from iotbx.map_manager import map_manager
from iotbx.map_model_manager import map_model_manager
from matplotlib import cm
from mmtbx.model.model import manager
from scipy.spatial import KDTree
from typing import List

from nanome.api import shapes, structure, PluginInstance
from nanome.util import Color, Logs, enums, Vector3

from .utils import cpk_colors, create_hidden_complex


class MapMesh:
    """Manages generated map from .map.gz file and renders as Mesh in workspace.

    Mesh is attached to a hidden complex, so that it is movable and scalable on its own.
    Map mesh also exposes mesh attributes such as upload and color(s).
    """

    def __init__(self, plugin, map_gz_file=None):
        self.__map_gz_file: str = map_gz_file
        self._plugin = plugin
        self.complex: structure.Complex = None
        self.mesh: shapes.Mesh = shapes.Mesh()
        self.mesh_inverted: shapes.Mesh = shapes.Mesh()
        self.backface = False
        self.map_manager: map_manager = None
        if map_gz_file:
            self.map_manager = self.load_map_file(map_gz_file)
            self.complex = self.create_map_complex()

    @property
    def map_gz_file(self):
        return self.__map_gz_file

    def add_map_gz_file(self, filepath: str):
        self.__map_gz_file = filepath
        self.map_manager = self.load_map_file(filepath)
        self.complex = self.create_map_complex(self.map_manager, filepath)

    @property
    def color(self):
        return self.mesh.color

    @color.setter
    def color(self, value: Color):
        self.mesh.color = value
        self.mesh_inverted.color = value

    @property
    def colors(self):
        return self.mesh.colors

    @colors.setter
    def colors(self, value: Color):
        self.mesh.colors = value
        self.mesh_inverted.colors = value

    def upload(self):
        self.mesh.upload()
        if self.backface:
            self.mesh_inverted.upload()

    async def load(self, isovalue, opacity, map_data=None, selected_residues=None):
        """Create complex, Generate Mesh, and attach mesh to complex."""
        selected_residues = selected_residues or []
        if map_data is None:
            map_data = self.map_manager.map_data().as_numpy_array()

        self._generate_mesh(map_data, isovalue, opacity, selected_residues)
        if self.complex.index == -1:
            # Create complex to attach mesh to.
            self.complex.boxed = True
            self.complex.locked = True
            [self.complex] = await self._plugin.add_to_workspace([self.complex])
            anchor = self.mesh.anchors[0]
            anchor.anchor_type = enums.ShapeAnchorType.Complex
            anchor.target = self.complex.index
            self.mesh_inverted.anchors[0] = anchor

    @staticmethod
    def load_map_file(map_gz_file):
        # Load map.gz file into map_manager
        dm = DataManager()
        with tempfile.NamedTemporaryFile(suffix='.mrc') as mrc_file:
            mrc_filepath = mrc_file.name
            with gzip.open(map_gz_file, 'rb') as f:
                mrc_file.write(f.read())
                map_manager = dm.get_real_map(mrc_filepath)
        return map_manager

    @staticmethod
    def create_map_complex(map_manager, map_gz_file: str):
        """Create complex which represents the map in the Entry list"""
        grid_min = map_manager.origin
        grid_max = map_manager.data.last()
        angstrom_min = map_manager.grid_units_to_cart(grid_min)
        angstrom_max = map_manager.grid_units_to_cart(grid_max)
        bounds = [angstrom_min, angstrom_max]
        comp = create_hidden_complex(map_gz_file, bounds)
        comp.boxed = True
        comp.locked = True
        comp.name = os.path.basename(map_gz_file)
        return comp

    def _generate_mesh(self, map_data, isovalue, opacity, selected_residues):
        Logs.debug("Generating Mesh from map...")
        Logs.debug("Marching Cubes...")
        vertices, triangles = mcubes.marching_cubes(map_data, isovalue)
        Logs.debug("Cubes Marched")
        # offset the vertices using the map origin
        # this makes sure the mesh is in the same coordinates as the molecule
        map_origin = self.map_manager.origin
        vertices += np.asarray(map_origin)

        # convert vertices from grid units to cartesian angstroms
        for i in range(vertices.shape[0]):
            vertices[i] = self.map_manager.grid_units_to_cart(vertices[i])

        Logs.debug("Simplifying mesh...")
        decimation_factor = 5
        target = max(1000, len(triangles) / decimation_factor)
        mesh_simplifier = pyfqmr.Simplify()
        mesh_simplifier.setMesh(vertices, triangles)
        mesh_simplifier.simplify_mesh(
            target_count=target, aggressiveness=7, preserve_border=True, verbose=0)
        Logs.debug("Mesh Simplified")
        vertices, triangles, normals = mesh_simplifier.getMesh()

        vertices = np.array(vertices).flatten()
        normals = np.array(normals).flatten()
        triangles = np.array(triangles).flatten()

        vertices = np.reshape(vertices, (int(len(vertices) / 3), 3))
        normals = np.reshape(normals, (int(len(normals) / 3), 3))
        triangles = np.reshape(triangles, (int(len(triangles) / 3), 3))

        # if selected_residues:
        #     vertices, normals, triangles = self.limit_view(
        #         vertices, normals, triangles, selected_residues)

        self.mesh.vertices = vertices.flatten()
        self.mesh.normals = normals.flatten()
        self.mesh.triangles = triangles.flatten()
        self.mesh_inverted.vertices = vertices.flatten()
        self.mesh_inverted.normals = np.array([-n for n in normals]).flatten()
        self.mesh_inverted.triangles = np.array([[t[1], t[0], t[2]] for t in triangles]).flatten()

        opacity_a = int(opacity * 255)
        self.mesh.color = Color(255, 255, 255, opacity_a)
        self.mesh_inverted.color = Color(255, 255, 255, opacity_a)
        Logs.message("Mesh generated")
        Logs.debug(f"{len(self.mesh.vertices) // 3} vertices")

    @property
    def map_origin(self):
        if hasattr(self, 'map_manager'):
            return self.map_manager.origin

    @staticmethod
    def limit_view(vertices, normals, triangles, selected_residues):
        if len(vertices) < 3 or not selected_residues:
            return

        atom_positions = []
        for residue in selected_residues:
            for a in residue.atoms:
                pos = a.position
                atom_positions.append(np.array([pos.x, pos.y, pos.z]))
        kdtree = KDTree(atom_positions)
        _, atom_pos_indices = kdtree.query(vertices, distance_upper_bound=2)

        vertices_to_keep = []
        mapping = []
        vertex_id = 0
        for vertex_index, atom_index in enumerate(atom_pos_indices):
            if atom_index >= 0 and atom_index < len(atom_positions):
                vertices_to_keep.append(vertex_index)
                mapping.append(vertex_id)
                vertex_id += 1
            else:
                mapping.append(-1)

        if len(vertices_to_keep) == len(vertices):
            return (vertices, normals, triangles)

        # Create new lists of vertices, normals, and triangles
        new_vertices = []
        new_triangles = []
        new_normals = []
        for i in vertices_to_keep:
            new_vertices.append(vertices[i])
            new_normals.append(normals[i])

        for t in triangles:
            updated_tri = [mapping[t[0]], mapping[t[1]], mapping[t[2]]]
            if -1 not in updated_tri:
                new_triangles.append(updated_tri)

        return (
            np.asarray(new_vertices).flatten(),
            np.asarray(new_normals).flatten(),
            np.asarray(new_triangles).flatten(),
        )

    @property
    def computed_vertices(self):
        # break up vertices list into list of lists
        if hasattr(self, 'mesh') and self.mesh:
            return np.asarray([
                self.mesh.vertices[x:x + 3]
                for x in range(0, len(self.mesh.vertices), 3)
            ])


class MapGroup:
    """Aggregates a MapMesh and its associated model complex."""

    def __init__(self, plugin, **kwargs):
        self._plugin = plugin
        self.group_name: str = kwargs.get("group_name", "")
        self.files: List[str] = kwargs.get("files", [])
        self.map_mesh = MapMesh(plugin)
        self.metadata = None

        self.hist_x_min = float('-inf')
        self.hist_x_max = float('inf')
        self.png_tempfile = None

        self.__visible = True
        self.position = [0.0, 0.0, 0.0]
        self.isovalue = 2.5
        self.opacity = 0.65
        self.radius = -1
        self.color_scheme = enums.ColorScheme.Element

        self._model: manager = None
        self.__model_complex: structure.Complex = None

    @property
    def model_complex(self):
        return self.__model_complex

    @property
    def map_gz_file(self):
        return self.map_mesh.map_gz_file

    @property
    def map_complex(self):
        return self.map_mesh.complex

    def add_pdb(self, pdb_file):
        dm = DataManager()
        self._model = dm.get_model(pdb_file)

    async def add_map_gz(self, map_gz_file):
        self.map_mesh.add_map_gz_file(map_gz_file)

    def add_model_complex(self, comp):
        self.__model_complex = comp
        if self.map_complex:
            self.map_complex.locked = True
            self.map_complex.position = comp.position
            self.map_complex.rotation = comp.rotation
        if self.map_mesh.mesh:
            self.color_by_scheme(self.map_mesh, self.color_scheme)

    def generate_histogram(self, temp_dir: str):
        Logs.debug("Generating histogram...")
        start_time = time.time()
        flat = np.array(self.map_mesh.map_manager.map_data().as_1d(), dtype=np.float32)
        minmap = np.min(flat)
        flat_offset = flat + abs(minmap) + 0.001
        hist, bins = np.histogram(flat_offset, bins=1000)
        logbins = np.logspace(np.log10(bins[0]), np.log10(bins[-1]), len(bins))
        bins = logbins - abs(minmap)
        plt.figure(figsize=(8, 3))
        plt.hist(flat, bins=bins)
        plt.ylim(bottom=10)
        plt.yscale('log')
        plt.title("Level histogram")
        self.hist_x_min, self.hist_x_max = plt.xlim()
        self.png_tempfile = tempfile.NamedTemporaryFile(
            delete=False, suffix=".png", dir=temp_dir)
        plt.savefig(self.png_tempfile.name)
        end_time = time.time()
        elapsed_time = round(end_time - start_time, 1)
        Logs.debug(
            f"Histogram Generated in {elapsed_time} seconds",
            extra={"elapsed_time": elapsed_time})
        return self.png_tempfile.name

    async def update_color(self, color_scheme, opacity):
        self.opacity = opacity
        self.color_scheme = color_scheme
        if self.map_mesh.mesh is not None:
            self.map_mesh.color = Color(255, 255, 255, int(opacity * 255))
            self.color_by_scheme(self.map_mesh, color_scheme)
            self.map_mesh.upload()

    async def generate_mesh(self, use_selected_residues=False):
        # Compute iso-surface with marching cubes algorithm
        Logs.message("Generating mesh...")
        # Set up map model manager
        kwargs = {
            'ignore_symmetry_conflicts': True
        }
        model = None
        if hasattr(self, '_model') and self._model:
            model = self._model
            kwargs['model'] = model
        if hasattr(self, 'map_mesh'):
            kwargs['map_manager'] = self.map_mesh.map_manager
        mmm = map_model_manager(**kwargs)
        Logs.debug("Generating Map...")
        mmm.generate_map()
        Logs.debug("Map Generated")
        map_data = mmm.map_manager().map_data().as_numpy_array()

        # Get selected residues
        selected_residues = []
        if use_selected_residues and self.model_complex:
            await self.refresh_model_complex()
            model_comp = self.model_complex
            selected_residues = [
                res for res in model_comp.residues
                if any([atom.selected for atom in res.atoms])
            ]
        await self.map_mesh.load(
            self.isovalue, self.opacity, map_data=map_data,
            selected_residues=selected_residues)
        self.color_by_scheme(self.map_mesh, self.color_scheme)
        self.map_mesh.upload()
        self._set_hist_x_min_max()

    def color_by_scheme(self, map_mesh, scheme):
        Logs.message(f"Coloring Mesh with scheme {scheme.name}")
        if not self.model_complex:
            Logs.debug("No model set to color by. Returning")
            return
        comp = self.model_complex
        if scheme == enums.ColorScheme.Element:
            self.color_by_element(map_mesh, comp)
        elif scheme == enums.ColorScheme.BFactor:
            self.color_by_bfactor(map_mesh, comp)
        elif scheme == enums.ColorScheme.Chain:
            self.color_by_chain(map_mesh, comp)
        map_mesh.upload()
        Logs.message("Mesh colored")

    def color_by_element(self, map_mesh, model_complex):
        verts = map_mesh.computed_vertices
        if len(verts) < 3:
            return
        atom_positions = []
        atoms = []
        for a in model_complex.atoms:
            atoms.append(a)
            p = a.position
            atom_positions.append(np.array([p.x, p.y, p.z]))
        kdtree = KDTree(atom_positions)
        _, indices = kdtree.query(verts, distance_upper_bound=2)
        colors = np.array([], dtype=np.uint8)
        for i in indices:
            if i >= 0 and i < len(atom_positions):
                colors = np.append(colors, cpk_colors(atoms[i]))
            else:
                colors = np.append(colors, [255, 255, 255, 50])
        map_mesh.colors = colors

    def color_by_chain(self, map_mesh: MapMesh, model_complex: structure.Complex):
        verts = map_mesh.computed_vertices
        if len(verts) < 3:
            return

        molecule = model_complex._molecules[model_complex.current_frame]
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
            for _ in c.atoms:
                color_per_atom.append(chain_color)

        colors = np.array([], dtype=np.uint8)
        # No need for neighbor search as all vertices have the same color
        if n_chain == 1:
            for i in range(len(verts)):
                colors = np.append(colors, color_per_atom[0])
            map_mesh.colors = colors
            return

        atom_positions = []
        atoms = []
        for a in model_complex.atoms:
            atoms.append(a)
            p = a.position
            atom_positions.append(np.array([p.x, p.y, p.z]))

        # Create a KDTree for fast neighbor search
        # Look for the closest atom near each vertex
        kdtree = KDTree(np.array(atom_positions))
        _, indices = kdtree.query(
            verts, distance_upper_bound=20)
        for i in indices:
            if i >= 0 and i < len(atom_positions):
                colors = np.append(colors, color_per_atom[i])
            else:
                colors = np.append(colors, [255, 255, 255, 0])
        map_mesh.colors = colors

    def color_by_bfactor(self, map_mesh: MapMesh, model_complex: structure.Complex):
        verts = map_mesh.computed_vertices
        if len(verts) < 3:
            return

        sections = 128
        cm_subsection = np.linspace(0.0, 1.0, sections)
        colors_rainbow = [cm.jet(x) for x in cm_subsection]

        atom_positions = []
        atoms = []
        for a in model_complex.atoms:
            atoms.append(a)
            p = a.position
            atom_positions.append(np.array([p.x, p.y, p.z]))

        # Create a KDTree for fast neighbor search
        # Look for the closest atom near each vertex
        kdtree = KDTree(np.array(atom_positions))
        _, indices = kdtree.query(
            verts, distance_upper_bound=20)

        colors = np.array([], dtype=np.uint8)
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
                colors = np.append(colors, colors_rainbow[int(id_color)])
            else:
                colors = np.append(colors, [255, 255, 255, 0])
        map_mesh.colors = colors

    @property
    def visible(self):
        return self.__visible

    @visible.setter
    def visible(self, value):
        self.__visible = value
        if self.map_complex:
            self.map_mesh.complex.visible = value
        if self.model_complex:
            self.model_complex.visible = value

    def has_map(self):
        return self.map_mesh.complex is not None

    def has_histogram(self):
        return self.hist_x_min != float('-inf')

    def remove_group_objects(self, comp_list):
        comps_to_delete = []
        if self.model_complex in comp_list:
            comps_to_delete.append(self.model_complex)
            self.__model_complex = None
        if self.map_complex in comp_list:
            comps_to_delete.append(self.map_complex)
            self.map_mesh = MapMesh(self._plugin)
        self._plugin.remove_from_workspace(comps_to_delete)

    def _set_hist_x_min_max(self):
        flat = list(self.map_mesh.map_manager.map_data().as_1d())
        self.hist_x_min = np.min(flat)
        self.hist_x_max = np.max(flat)

    async def refresh_model_complex(self):
        [self.__model_complex] = await self._plugin.request_complexes([self.model_complex.index])

    async def limit_to_selection(self):
        # Compute iso-surface with marching cubes algorithm
        Logs.message("Limiting to selected residues...")

        # Get selected residues
        selected_residues = []
        await self.refresh_model_complex()
        model_comp = self.model_complex
        selected_residues = [
            res for res in model_comp.residues
            if any([atom.selected for atom in res.atoms])
        ]
        mesh = self.map_mesh.mesh
        vertices = mesh.vertices
        triangles = mesh.triangles
        normals = mesh.normals

        vertices = np.reshape(vertices, (int(len(vertices) / 3), 3))
        normals = np.reshape(normals, (int(len(normals) / 3), 3))
        triangles = np.reshape(triangles, (int(len(triangles) / 3), 3))

        vertices, normals, triangles = self.map_mesh.limit_view(
            vertices, normals, triangles, selected_residues)

        new_mesh = shapes.Mesh()
        new_mesh.vertices = vertices
        new_mesh.normals = normals
        new_mesh.triangles = triangles
        new_mesh.anchors = self.map_mesh.mesh.anchors
        new_mesh.colors = []
        shapes.Shape.destroy(self.map_mesh.mesh)
        self.map_mesh.mesh = new_mesh
        # self.map_mesh.mesh_inverted.vertices = vertices.flatten()
        # self.map_mesh.mesh_inverted.normals = np.array([-n for n in normals]).flatten()
        # self.map_mesh.mesh_inverted.triangles = np.array([[t[1], t[0], t[2]] for t in triangles]).flatten()
        self.map_mesh.mesh.upload(self.print_uploaded)

        verts = np.reshape(new_mesh.vertices, (int(len(new_mesh.vertices) / 3), 3))
        norms = np.reshape(new_mesh.normals, (int(len(new_mesh.normals) / 3), 3))
        tris = np.reshape(new_mesh.triangles, (int(len(new_mesh.triangles) / 3), 3))

        f = open("DebugMesh.obj", "w")

        for v in verts:
            # f.write("v %.3f %.3f %.3f\n".format(verts[0], verts[1], verts[2]))
            f.write(f"v {v[0]} {v[1]} {v[2]}\n")

        for n in norms:
            # f.write("vn %.3f %.3f %.3f\n".format(norms[0], norms[1], norms[2]))
            f.write(f"vn {n[0]} {n[1]} {n[2]}\n")

        for t in tris:
            # f.write("f %d %d %d\n".format(tris[0] + 1, tris[1] + 1, tris[2] + 1))
            f.write(f"f {t[0] + 1} {t[1] + 1} {t[2] + 1}\n")

        f.close()

    def print_uploaded(self, *args, **kwargs):
        print("Uploaded")


class ViewportEditor:

    DEFAULT_RADIUS = 15

    def __init__(self, plugin_instance: PluginInstance, map_group: MapGroup):
        self.map_group = map_group
        self.plugin = plugin_instance
        self.is_editing = False
        self.complex = None
        self.sphere = None

    async def enable(self):
        Logs.message("Enabling viewport editor")
        if not self.complex:
            [self.complex] = await self.plugin.add_to_workspace([
                create_hidden_complex(self.map_group.map_complex.full_name)
            ])
        if not self.sphere:
            # create viewport sphere
            self.sphere = shapes.Sphere()
            preset_radius = self.map_group.radius
            self.sphere.radius = preset_radius if preset_radius > 0 else self.DEFAULT_RADIUS
            self.sphere.color = Color(0, 0, 200, 127)

            anchor = self.sphere.anchors[0]
            anchor.anchor_type = enums.ShapeAnchorType.Complex
            anchor.target = self.complex.index
        shapes.Shape.upload(self.sphere)

    def disable(self):
        Logs.message("Hiding viewport editor")
        if self.complex:
            self.plugin.remove_from_workspace([self.complex])
            self.complex = None
        if self.sphere:
            shapes.Shape.destroy(self.sphere)
            self.sphere = None
        self.plugin.update_structures_shallow([self.map_group.map_complex])

    async def apply(self):
        """Apply viewport position and radius to MapGroup."""
        Logs.message("Applying Viewport")
        if not self.sphere:
            Logs.warning("Missing Sphere, can not apply Viewport. Disabling.")
            self.disable()
            return
        # Get latest states of viewport complex and mapgroup
        viewport_comp_index = self.complex.index
        [viewport_comp] = await self.plugin.request_complexes([viewport_comp_index])
        # get viewport complex position
        c_to_w = viewport_comp.get_complex_to_workspace_matrix()
        pos = c_to_w * Vector3(*self.map_group.position)

        # set mapgroup radius and position
        self.map_group.position = [*pos]
        self.map_group.radius = self.sphere.radius

        # update mapgroup complex
        self.plugin.update_structures_shallow([self.map_group.map_complex])
        # redraw map
        await self.map_group.generate_mesh()

    def update_radius(self, radius):
        self.sphere.radius = radius
        self.sphere.upload()
