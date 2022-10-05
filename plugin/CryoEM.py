import os
import tempfile
import time

import nanome
from nanome.util import Logs, enums, async_callback

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
        if group:
            group.add_pdb(filepath)
        self.send_files_to_load([filepath])
        # Get new complex, and associate to MapGroup
        if group:
            time.sleep(1)  # Give time for PDB to load
            shallow_comp = (await self.request_complex_list())[0]
            comp = (await self.request_complexes([shallow_comp.index]))[0]
            group.add_nanome_complex(comp)
            group.generate_mesh()
            group.mesh.upload()

    async def create_mapgroup_for_file(self, map_gz_filepath):
        path, ext = os.path.splitext(map_gz_filepath)
        group = next(iter(self.groups.values()), None)
        group_name = os.path.basename(path)
        group = MapGroup(group_name=group_name)
        group.add_map_gz(map_gz_filepath)
        self.groups[group_name] = group

        # Check if theres a complex we can align to
        # Probably not the end behavior we want, but
        # it works at this stage of prototyping
        complexes = await self.request_complex_list()
        if complexes:
            comp = complexes[0]
            deep_comp = (await self.request_complexes([comp.index]))[0]
            group.add_nanome_complex(deep_comp)
        await self.render_mesh(group)
        self.menu.render()

    async def render_mesh(self, map_group: MapGroup):
        self.set_plugin_list_button(enums.PluginListButtonType.run, "Running...", False)
        Logs.message(f"Generating iso-surface for iso-value {round(map_group.isovalue, 3)}")
        mesh = map_group.generate_mesh()
        Logs.message(f"Uploading iso-surface ({len(mesh.vertices)} vertices)")
        await mesh.upload()
        Logs.message("Uploading completed")
        self.set_plugin_list_button(enums.PluginListButtonType.run, "Run", True)

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
        map_group.isovalue = 3.46
        map_group.opacity = 0.65

        # Load pdb and associate resulting complex with MapGroup
        await self.send_files_to_load([pdb_file])
        shallow_comp = (await self.request_complex_list())[0]
        comp = (await self.request_complexes([shallow_comp.index]))[0]
        map_group.add_nanome_complex(comp)
        mesh = map_group.generate_mesh()
        anchor = mesh.anchors[0]
        anchor.anchor_type = enums.ShapeAnchorType.Complex
        anchor.target = comp.index
        await mesh.upload()
        return map_group


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
