import gzip
import mcubes
import matplotlib.pyplot as plt
import numpy as np
import pyfqmr
import randomcolor
import tempfile
# from gridData import Grid
from iotbx.data_manager import DataManager
from iotbx.map_model_manager import map_model_manager
from matplotlib import cm
from nanome.api.shapes import Mesh
from nanome.util import Logs, enums, Color  # , Vector3
from scipy.spatial import KDTree
from .utils import cpk_colors


class MapGroup:

    def __init__(self, **kwargs):
        self.group_name = kwargs.get("group_name", "")
        self.files = kwargs.get("files", [])
        self.mesh = None
        self.nanome_complex = None
        self._manager = map_model_manager()
        self._map_voxel_size = None

        self.hist_x_min = 0.0
        self.hist_x_max = 1.0

        self.computed_normals = []
        self.computed_triangles = []
        self.wire_vertices = []
        self.wire_normals = []
        self.wire_triangles = []

        self.visible = True
        self.position = [0.0, 0.0, 0.0]
        self.isovalue = 0.1
        self.opacity = 0.65
        self.radius = 15
        self.color_scheme = enums.ColorScheme.Element
        self.wireframe_mode = False

    @property
    def _map_origin(self):
        return self._manager.map_manager().get_origin()

    @property
    def computed_vertices(self):
        # break up vertices list into list of lists
        if hasattr(self, 'mesh') and self.mesh:
            return np.asarray([
                self.mesh.vertices[x:x + 3]
                for x in range(0, len(self.mesh.vertices), 3)
            ])

    def add_pdb(self, pdb_file):
        dm = DataManager()
        model = dm.get_model(pdb_file)
        self._manager.set_model(model)

    def add_map_gz(self, map_gz_file):
        dm = DataManager()
        # Unpack map.gz
        with tempfile.NamedTemporaryFile(suffix='.mrc') as mrc_file:
            mrc_filepath = mrc_file.name
            with gzip.open(map_gz_file, 'rb') as f:
                with open(mrc_filepath, 'wb') as out:
                    out.write(f.read())
            map_mgr = dm.get_real_map(mrc_filepath)
            # Recreate manager, because I'm not sure how to
            # add map after mmm initialization
            self._manager = map_model_manager(
                model=self._manager.model(),
                map_manager=map_mgr)

    def generate_map(self):
        self._manager.generate_map()

    def add_file(self, filepath: str):
        self.files.append(filepath)
        if not filepath.endswith('pdb'):
            self.load_map(filepath)

    def generate_histogram(self, temp_dir: str):
        flat = list(self._manager.map_manager().map_data().as_1d())
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

    def set_limited_view_on_cog(self):
        # Compute center of gravity of structure
        cog = np.array([0.0, 0.0, 0.0])
        if self.nanome_complex is None:
            self.position = cog.tolist()
            return
        count = 0
        for a in self.nanome_complex.atoms:
            count += 1
            cog += np.array([a.position.x, a.position.y, a.position.z])
        cog /= count
        cog -= self._map_origin
        self.position = cog.tolist()

    async def update_color(self, color_scheme, opacity):
        self.opacity = opacity
        self.color_scheme = color_scheme
        if self.mesh is not None:
            self.mesh.color = Color(255, 255, 255, int(opacity * 255))
            self.color_by_scheme(self.mesh, color_scheme)

    def generate_mesh(self, isovalue, color_scheme=None, opacity=0.65, decimation_factor=5):
        # Compute iso-surface with marching cubes algorithm
        color_scheme = color_scheme or self.color_scheme
        # self.set_limited_view_on_cog()
        self.isovalue = isovalue
        self.opacity = opacity
        self.color_scheme = color_scheme

        self._manager.box_all_maps_around_model_and_shift_origin(box_cushion=3)
        map_mgr = self._manager.map_manager()
        map_data = map_mgr.map_data().as_numpy_array()
        vertices, triangles = mcubes.marching_cubes(map_data, isovalue)
        np_vertices = np.asarray(vertices)
        np_triangles = np.asarray(triangles)
        Logs.debug("Decimating mesh")
        target = max(1000, len(np_triangles) / decimation_factor)
        mesh_simplifier = pyfqmr.Simplify()
        mesh_simplifier.setMesh(np_vertices, np_triangles)
        mesh_simplifier.simplify_mesh(
            target_count=target, aggressiveness=7, preserve_border=True, verbose=0
        )
        vertices, triangles, normals = mesh_simplifier.getMesh()
        voxel_sizes = map_mgr.pixel_sizes()
        if voxel_sizes[0] > 0.0001:
            Logs.debug("Setting voxels")
            voxel_size = np.array(voxel_sizes)
            vertices *= voxel_size

        Logs.debug("Setting computed values")
        computed_vertices = np.array(vertices)
        computed_normals = np.array(normals)
        computed_triangles = np.array(triangles)
        if not hasattr(self, 'mesh') or not self.mesh:
            self.mesh = Mesh()
        self.mesh.vertices = computed_vertices.flatten()
        self.mesh.normals = computed_normals.flatten()
        self.mesh.triangles = computed_triangles.flatten()

        self.mesh.color = Color(255, 255, 255, int(opacity * 255))
        self.color_by_scheme(self.mesh, color_scheme)
        return self.mesh

    def color_by_scheme(self, mesh, scheme):
        if scheme == enums.ColorScheme.Element:
            self.color_by_element(mesh)
        elif scheme == enums.ColorScheme.BFactor:
            self.color_by_bfactor(mesh)
        elif scheme == enums.ColorScheme.Chain:
            self.color_by_chain(mesh)

    def color_by_element(self, mesh):
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
            verts + self._map_origin, distance_upper_bound=2)
        colors = []
        for i in indices:
            if i >= 0 and i < len(atom_positions):
                colors += cpk_colors(atoms[i])
            else:
                colors += [0.0, 0.0, 0.0, 1.0]
        mesh.colors = np.array(colors)

    def color_by_chain(self, mesh):
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
            mesh.colors = np.array(colors)
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
        mesh.colors = np.array(colors)

    def color_by_bfactor(self, mesh):
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
        mesh.colors = np.array(colors)

    def limit_view(self, mesh: tuple, position: list, range: float):
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

    def toggle_wireframe_mode(self, toggle: bool):
        self.wireframe_mode = toggle
        if not self.mesh:
            return
        if toggle:
            wire_vertices, wire_normals, wire_triangles = self.wireframe_mesh()
            self.mesh.vertices = wire_vertices.flatten()
            self.mesh.triangles = wire_triangles.flatten()
        else:
            self.mesh.vertices = np.asarray(self.computed_vertices).flatten()
            self.mesh.triangles = np.asarray(self.computed_triangles).flatten()

    def wireframe_mesh(self, wiresize=0.03):
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
