import os
import tempfile
import nanome
import numpy as np
import mcubes
import pyfqmr

from nanome.api.shapes import Mesh
from nanome.util import Logs, enums, Color, async_callback
from iotbx.data_manager import DataManager
from iotbx.map_model_manager import map_model_manager

from .menu import MainMenu, SearchMenu
from .models import MapGroup


class CryoEM(nanome.AsyncPluginInstance):

    @async_callback
    async def start(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.menu = MainMenu(self)
        self.search_menu = SearchMenu(self)
        self.groups = {}

    async def load_map_and_model(self):
        Logs.message("Loading Map file")
        # # map_gz_file = "emd_30288.map.gz"
        pdb_file = "7c4u.pdb"

        dm = DataManager()
        dm.set_overwrite(True)

        model = dm.get_model(pdb_file)
        mmm = map_model_manager(model=model)
        mmm.generate_map()

        mrc_file = 'map.mrc'
        pdb_file = 'model.pdb'
        mmm.write_map(mrc_file)
        mmm.write_model(pdb_file)

        iso = 0.5
        opacity = 0.65
        color_scheme = enums.ColorScheme.BFactor
        mesh = self.generate_mesh(mmm.map_manager(), iso, color_scheme, opacity)
        await self.send_files_to_load([pdb_file])
        comp = (await self.request_complex_list())[0]
        anchor = mesh.anchors[0]
        anchor.anchor_type = enums.ShapeAnchorType.Complex
        anchor.target = comp.index
        await mesh.upload()
        return

        selection_string = 'resseq 1:100'
        box_mmm = mmm.extract_all_maps_around_model(selection_string=selection_string)
        # Write boxed residue range to files
        # boxed_map_filename = os.path.join(self.temp_dir.name, os.path.basename(mrc_file))
        boxed_map_filename = os.path.join("map_boxed.mrc")
        dm.write_real_map_file(
            box_mmm.map_manager(),
            filename=boxed_map_filename)

        boxed_model_filename = os.path.join(self.temp_dir.name, os.path.basename(pdb_file))
        dm.write_model_file(
            box_mmm.model(),
            filename=boxed_model_filename,
            extension="pdb")
        # Generate mesh to upload to Nanome
        iso = 1.48
        opacity = 0.65
        color_scheme = enums.ColorScheme.BFactor

        mm = box_mmm.map_manager()
        mesh = self.generate_mesh(mm, iso, color_scheme, opacity)

        await self.send_files_to_load([boxed_model_filename])
        comp = (await self.request_complex_list())[0]
        anchor = mesh.anchors[0]
        anchor.anchor_type = enums.ShapeAnchorType.Complex
        anchor.target = comp.index
        await mesh.upload()

    def generate_mesh(self, map_manager, iso, color_scheme, opacity=0.65, decimation_factor=5):
        # Compute iso-surface with marching cubes algorithm
        # self.set_limited_view_on_cog()
        map_data = map_manager.map_data().as_numpy_array()
        vertices, triangles = mcubes.marching_cubes(map_data, iso)
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
        voxel_sizes = map_manager.pixel_sizes()
        if voxel_sizes[0] > 0.0001:
            Logs.debug("Setting voxels")
            voxel_size = np.array(voxel_sizes)
            vertices *= voxel_size

        Logs.debug("Setting computed values")
        computed_vertices = np.array(vertices)
        computed_normals = np.array(normals)
        computed_triangles = np.array(triangles)
        mesh = Mesh()
        mesh.vertices = computed_vertices.flatten()
        mesh.normals = computed_normals.flatten()
        mesh.triangles = computed_triangles.flatten()

        mesh.color = Color(255, 255, 255, int(opacity * 255))
        mesh
        # if self.nanome_complex is not None:
        #     anchor.anchor_type = enums.ShapeAnchorType.Complex
        #     anchor.target = self.nanome_complex.index
        # if self.wireframe_mode:
        #     self.wire_vertices, self.wire_normals, self.wire_triangles = self.wireframe_mesh()
        #     mesh.vertices = np.asarray(self.wire_vertices).flatten()
        #     mesh.triangles = np.asarray(self.wire_triangles).flatten()
        # self.color_by_scheme(mesh, color_scheme)
        return mesh

    def on_stop(self):
        self.temp_dir.cleanup()

    @async_callback
    async def on_run(self):
        # complexes = await self.request_complex_list()
        # self.menu.render(complexes, force_enable=True)
        await self.load_map_and_model()
        pass

    def enable_search_menu(self):
        self.search_menu.render(force_enable=True)

    async def add_to_group(self, filepath):
        path, ext = os.path.splitext(filepath)
        if ext == ".pdb":
            group_name = os.path.basename(path)
            group = MapGroup(group_name=group_name)
            group.add_file(filepath)
            self.groups[group_name] = group
            self.send_files_to_load([filepath])
        else:
            # For now just add maps to first group
            # Will need to be fixed later
            group = next(iter(self.groups.values()), None)
            if not group:
                group_name = os.path.basename(path)
                group = MapGroup(group_name=group_name)
            group.add_file(filepath)
            await self.render_mesh(group)
        complexes = await self.request_complex_list()
        self.menu.render(complexes)

    async def render_mesh(self, map_group: map_model_manager):
        self.set_plugin_list_button(enums.PluginListButtonType.run, "Running...", False)
        iso = 0.1
        opacity = 0.65
        self.radius = 15
        color_scheme = enums.ColorScheme.BFactor
        comps = await self.request_complex_list()
        if comps:
            deep_comp = await self.request_complexes([comps[0].index])
            map_group.nanome_complex = deep_comp[0]
        else:
            map_group.nanome_complex = None
        Logs.message(f"Generating iso-surface for iso-value {round(iso, 3)}")
        # mesh = self.generate_mesh(mm, iso, color_scheme, opacity)
        Logs.message(f"Uploading iso-surface ({len(mesh.vertices)} vertices)")
        await mesh.upload()
        self.set_plugin_list_button(enums.PluginListButtonType.run, "Run", True)


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
