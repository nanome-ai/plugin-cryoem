import os
import tempfile
from pathlib import Path

import nanome
from nanome.util import Logs, enums, async_callback
from nanome.api import structure
from .menu import MainMenu, SearchMenu
from .models import MapGroup


class CryoEM(nanome.AsyncPluginInstance):

    @async_callback
    async def start(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.menu = MainMenu(self)
        self.search_menu = SearchMenu(self)
        self.groups = {}

    def on_stop(self):
        self.temp_dir.cleanup()

    @async_callback
    async def on_run(self):
        # await self.load_map_and_model()
        self.menu.render(force_enable=True)

    def enable_search_menu(self):
        self.search_menu.render(force_enable=True)

    async def add_pdb_to_group(self, filepath):
        # Look for a MapGroup to add the model to
        group = next(iter(self.groups.values()), None)
        comp = structure.Complex.io.from_pdb(path=filepath)
        # Get new complex, and associate to MapGroup
        comp.name = Path(filepath).stem
        await self.add_bonds([comp])
        if group:
            group.add_pdb(filepath)
            # align complex to mapmesh
            mesh_complex = group.map_mesh.complex
            comp.position = mesh_complex.position
            comp.rotation = mesh_complex.rotation
            comp.locked = True
            comp.boxed = False
        [created_comp] = await self.add_to_workspace([comp])
        if group:
            group.add_model_complex(created_comp)

    async def create_mapgroup_for_file(self, map_gz_filepath, isovalue=None):
        path, ext = os.path.splitext(map_gz_filepath)
        group = next(iter(self.groups.values()), None)
        group_name = os.path.basename(path)
        group = MapGroup(self, group_name=group_name)
        if isovalue:
            Logs.debug(f"Setting isovalue to {isovalue}")
            group.isovalue = isovalue
        await group.add_map_gz(map_gz_filepath)
        self.groups[group_name] = group

        # Check if theres a complex we can align to
        # Probably not the end behavior we want, but
        # it works at this stage of prototyping
        complexes = await self.request_complex_list()
        if complexes:
            comp = complexes[0]
            deep_comp = (await self.request_complexes([comp.index]))[0]
            group.add_model_complex(deep_comp)
            group.map_mesh.complex.position = deep_comp.position
            group.map_mesh.complex.rotation = deep_comp.rotation
            self.update_structures_deep([group.map_mesh.complex])
        await group.generate_mesh()
        self.menu.render()

    async def load_map_and_model(self):
        """Function for development that loads a map and model from the fixtures folder.

        This is useful for validating that a map and model can still aligned correctly in the worspace
        Having every step in one function can be useful for perspective
        """
        Logs.message("Loading Map and PDB file")
        fixtures_path = os.path.join(os.getcwd(), 'tests', 'fixtures')
        map_gz_file = os.path.join(fixtures_path, 'emd_30288.map.gz')
        pdb_file = os.path.join(fixtures_path, "7c4u.pdb")

        map_group = MapGroup()
        map_group.add_pdb(pdb_file)
        map_group.add_map_gz(map_gz_file)
        map_group.isovalue = 2.5
        map_group.opacity = 0.65

        # Load pdb and associate resulting complex with MapGroup
        await self.send_files_to_load([pdb_file])
        shallow_comp = (await self.request_complex_list())[0]
        comp = (await self.request_complexes([shallow_comp.index]))[0]
        map_group.add_model_complex(comp)
        mesh = map_group.generate_mesh()
        anchor = mesh.anchors[0]
        anchor.anchor_type = enums.ShapeAnchorType.Complex
        anchor.target = comp.index
        await mesh.upload()
        return map_group

    async def delete_mapgroup(self, map_group: MapGroup):
        map_comp = map_group.map_mesh.complex
        model_comp = map_group.model_complex
        comps_to_delete = [map_comp]
        if model_comp:
            comps_to_delete.append(model_comp)
        await self.remove_from_workspace(comps_to_delete)
        del self.groups[map_group.group_name]
        self.menu.render()


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
