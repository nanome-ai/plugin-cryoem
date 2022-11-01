import gzip
import os
import tempfile

import matplotlib.pyplot as plt
import mcubes
import numpy as np
import pyfqmr
import randomcolor
from typing import List
from iotbx.data_manager import DataManager
from iotbx.map_manager import map_manager
from iotbx.map_model_manager import map_model_manager
from mmtbx.model.model import manager

from matplotlib import cm
from scipy.spatial import KDTree

import nanome
from nanome.api import shapes, structure
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
        self.map_manager: map_manager = None
        self.wireframe_mode: bool = False
        self.wireframe_vertices: List[float] = []
        if map_gz_file:
            self._load_map_file()

    @property
    def map_gz_file(self):
        return self.__map_gz_file

    def add_map_gz_file(self, filepath):
        self.__map_gz_file = filepath
        self._load_map_file()

    def _load_map_file(self):
        dm = DataManager()
        self.complex = create_hidden_complex(self.map_gz_file)
        with tempfile.NamedTemporaryFile(suffix='.mrc') as mrc_file:
            mrc_filepath = mrc_file.name
            with gzip.open(self.map_gz_file, 'rb') as f:
                mrc_file.write(f.read())
                self.map_manager = dm.get_real_map(mrc_filepath)
                self.complex.name = os.path.basename(self.map_gz_file)

    @property
    def color(self):
        return self.mesh.color

    @color.setter
    def color(self, value: Color):
        self.mesh.color = value

    @property
    def colors(self):
        return self.mesh.colors

    @colors.setter
    def colors(self, value: Color):
        self.mesh.colors = value

    def upload(self):
        self.mesh.upload()

    async def load(self, isovalue, opacity, radius, position, map_data=None):
        """Create complex, Generate Mesh, and attach mesh to complex."""
        if map_data is None:
            map_data = self.map_manager.map_data().as_numpy_array()
        self._generate_mesh(map_data, isovalue, opacity, radius, position)
        if self.complex.index == -1:
            # Create complex to attach mesh to.
            self.complex.boxed = True
            self.complex.locked = True
            [self.complex] = await self._plugin.add_to_workspace([self.complex])
            anchor = self.mesh.anchors[0]
            anchor.anchor_type = enums.ShapeAnchorType.Complex
            anchor.target = self.complex.index

    def _generate_mesh(self, map_data, isovalue, opacity, radius, position):
        Logs.debug("Generating Mesh from map...")
        Logs.debug("Marching Cubes...")
        vertices, triangles = mcubes.marching_cubes(map_data, isovalue)
        Logs.debug("Cubes Marched")
        # offset the vertices using the map origin
        # this makes sure the mesh is in the same coordinates as the molecule
        map_origin = self.map_manager.origin
        vertices += np.asarray(map_origin)
        np_vertices = np.asarray(vertices)
        np_triangles = np.asarray(triangles)
        Logs.debug("Simplifying mesh...")
        decimation_factor = 5
        target = max(1000, len(np_triangles) / decimation_factor)
        mesh_simplifier = pyfqmr.Simplify()
        mesh_simplifier.setMesh(np_vertices, np_triangles)
        mesh_simplifier.simplify_mesh(
            target_count=target, aggressiveness=7, preserve_border=True, verbose=0)
        Logs.debug("Mesh Simplified")
        vertices, triangles, normals = mesh_simplifier.getMesh()
        voxel_sizes = self.map_manager.pixel_sizes()
        if voxel_sizes[0] > 0.0001:
            Logs.debug("Setting voxels")
            voxel_size = np.array(voxel_sizes)
            vertices *= voxel_size

        computed_vertices = np.array(vertices)
        computed_normals = np.array(normals)
        computed_triangles = np.array(triangles)
        Logs.debug("Limiting view...")
        vertices, normals, triangles = self.limit_view(
            computed_vertices, computed_normals, computed_triangles, radius, position)

        self.mesh.vertices = vertices.flatten()
        self.mesh.normals = normals.flatten()
        self.mesh.triangles = triangles.flatten()

        self.mesh.color = Color(255, 255, 255, int(opacity * 255))
        self.mesh.upload()
        Logs.message("Mesh generated")
        Logs.debug(f"{len(self.mesh.vertices) // 3} vertices")

    def limit_view(self, vertices, normals, triangles, radius, position):
        if radius <= 0:
            return (vertices, normals, triangles)

        pos = np.asarray(position)
        idv = 0
        to_keep = []
        for v in vertices:
            vert = np.asarray(v)
            dist = np.linalg.norm(vert - pos)
            if dist <= radius:
                to_keep.append(idv)
            idv += 1
        if len(to_keep) == len(vertices):
            return (vertices, normals, triangles)

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

        self.hist_x_min = 0.0
        self.hist_x_max = 1.0

        self.__visible = True
        self.position = [0.0, 0.0, 0.0]
        self.isovalue = 2.5
        self.opacity = 0.65
        self.radius = 15
        self.color_scheme = enums.ColorScheme.Element
        self.wireframe_mode: bool = False

        self._model: manager = None
        self.__model_complex: structure.Complex = None

    @property
    def model_complex(self):
        return self.__model_complex

    @property
    def map_gz_file(self):
        return self.map_mesh.map_gz_file

    def add_pdb(self, pdb_file):
        dm = DataManager()
        self._model = dm.get_model(pdb_file)

    async def add_map_gz(self, map_gz_file):
        # Unpack map.gz
        self.map_mesh.add_map_gz_file(map_gz_file)

    def add_model_complex(self, comp):
        self.__model_complex = comp
        if self.map_mesh.complex:
            self.map_mesh.complex.locked = True
            self.map_mesh.complex.position = comp.position
            self.map_mesh.complex.rotation = comp.rotation
        if self.map_mesh.mesh:
            self.color_by_scheme(self.map_mesh, self.color_scheme)

    def generate_histogram(self, temp_dir: str):
        flat = list(self.map_mesh.map_manager.map_data().as_1d())
        minmap = np.min(flat)
        flat_offset = flat + abs(minmap) + 0.001
        hist, bins = np.histogram(flat_offset, bins=1000)
        logbins = np.logspace(np.log10(bins[0]), np.log10(bins[-1]), len(bins))
        plt.figure(figsize=(8, 3))
        plt.hist(flat, bins=logbins - abs(minmap))
        plt.ylim(bottom=10)
        plt.yscale('log')
        plt.title("Level histogram")
        self.hist_x_min, self.hist_x_max = plt.xlim()
        self.png_tempfile = tempfile.NamedTemporaryFile(
            delete=False, suffix=".png", dir=temp_dir)
        plt.savefig(self.png_tempfile.name)
        return self.png_tempfile.name

    async def update_color(self, color_scheme, opacity):
        self.opacity = opacity
        self.color_scheme = color_scheme
        if self.map_mesh.mesh is not None:
            self.map_mesh.color = Color(255, 255, 255, int(opacity * 255))
            self.color_by_scheme(self.map_mesh, color_scheme)

    async def generate_mesh(self):
        # Compute iso-surface with marching cubes algorithm
        Logs.message("Generating mesh...")
        # Set up map model manager
        kwargs = {
            'ignore_symmetry_conflicts': True
        }
        if hasattr(self, '_model'):
            kwargs['model'] = self._model
        if hasattr(self, 'map_mesh'):
            kwargs['map_manager'] = self.map_mesh.map_manager
        mmm = map_model_manager(**kwargs)
        Logs.debug("Generating Map...")
        mmm.generate_map()
        Logs.debug("Map Generated")
        map_data = mmm.map_manager().map_data().as_numpy_array()
        await self.map_mesh.load(self.isovalue, self.opacity, self.radius, self.position, map_data=map_data)
        self.color_by_scheme(self.map_mesh, self.color_scheme)
        self.map_mesh.upload()

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
        map_mesh.mesh.upload()
        Logs.message("Mesh colored")

    def color_by_element(self, map_mesh, model_complex):
        verts = map_mesh.computed_vertices if not map_mesh.wireframe_mode else map_mesh.wire_vertices
        if len(verts) < 3:
            return
        atom_positions = []
        atoms = []
        for a in model_complex.atoms:
            atoms.append(a)
            p = a.position
            atom_positions.append(np.array([p.x, p.y, p.z]))
        kdtree = KDTree(atom_positions)
        result, indices = kdtree.query(verts, distance_upper_bound=2)
        colors = []
        for i in indices:
            if i >= 0 and i < len(atom_positions):
                colors += cpk_colors(atoms[i])
            else:
                colors += [0.0, 0.0, 0.0, 1.0]
        map_mesh.colors = np.array(colors)

    def color_by_chain(self, map_mesh: MapMesh, model_complex: structure.Complex):
        verts = map_mesh.computed_vertices if not map_mesh.wireframe_mode else map_mesh.wire_vertices
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
            for atom in c.atoms:
                color_per_atom.append(chain_color)

        colors = []

        # No need for neighbor search as all vertices have the same color
        if n_chain == 1:
            for i in range(len(verts)):
                colors += color_per_atom[0]
            map_mesh.colors = np.array(colors)
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
        result, indices = kdtree.query(
            verts, distance_upper_bound=20)
        for i in indices:
            if i >= 0 and i < len(atom_positions):
                colors += color_per_atom[i]
            else:
                colors += [0.0, 0.0, 0.0, 1.0]
        map_mesh.colors = np.array(colors)

    def color_by_bfactor(self, map_mesh: MapMesh, model_complex: structure.Complex):
        verts = map_mesh.computed_vertices if not map_mesh.wireframe_mode else map_mesh.wire_vertices
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
        result, indices = kdtree.query(
            verts, distance_upper_bound=20)

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
        map_mesh.colors = np.array(colors)

    @property
    def visible(self):
        return self.__visible

    @visible.setter
    def visible(self, value):
        self.__visible = value
        if self.map_mesh.complex:
            self.map_mesh.complex.visible = value
        if self.model_complex:
            self.model_complex.visible = value

    def has_map(self):
        return self.map_mesh.complex is not None


class ViewportEditor:

    def __init__(self, map_group: MapGroup, plugin_instance: nanome.PluginInstance):
        self.map_group = map_group
        self.plugin = plugin_instance

        self.is_editing = False
        self.complex = None
        self.sphere = None

    async def toggle_edit(self, edit: bool):
        if not self.map_group.model_complex:
            Logs.warning("No model complex found")
            return
        self.is_editing = edit
        # Get latest position for map_mesh complex
        map_mesh_comp = self.map_group.map_mesh.complex
        complexes = await self.plugin.request_complex_list()
        mesh_complex = next(
            c for c in complexes
            if c.index == map_mesh_comp.index)

        if edit:
            Logs.debug("Creating Viewport...")
            # create viewport sphere and position at current map position
            comp_name = self.map_group.model_complex.name + ' (viewport)'
            self.complex = create_hidden_complex(comp_name)

            # calculate viewport position
            c_to_w = mesh_complex.get_complex_to_workspace_matrix()
            self.complex.position = c_to_w * Vector3(*self.map_group.position)

            # lock mesh position
            mesh_complex.locked = True
            self.plugin.update_structures_shallow([mesh_complex])

            res = await self.plugin.add_to_workspace([self.complex])
            self.complex.index = res[0].index

            # create viewport sphere
            sphere = shapes.Sphere()
            self.sphere = sphere
            sphere.radius = self.map_group.radius
            sphere.color = Color(100, 100, 100, 127)

            anchor = sphere.anchors[0]
            anchor.anchor_type = enums.ShapeAnchorType.Complex
            anchor.target = self.complex.index
            sphere.upload()
            Logs.debug("Viewport created")

        else:
            # get viewport position, transform into map space and set map position
            vp_complex = next(c for c in complexes if c.index == self.complex.index)

            # calculate viewport position
            w_to_c = mesh_complex.get_workspace_to_complex_matrix()
            vp_position = w_to_c * vp_complex.position
            self.map_group.position = [*vp_position]

            mesh_complex.boxed = False
            self.plugin.update_structures_shallow([mesh_complex])

            # remove viewport sphere
            self.sphere.destroy()
            self.plugin.remove_from_workspace([self.complex])
            self.complex = None
            self.sphere = None

    def update_radius(self, radius):
        self.sphere.radius = radius
        self.sphere.upload()
