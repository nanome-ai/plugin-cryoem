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

    async def load_map_and_model(self):
        Logs.message("Loading Map and PDB file")
        map_gz_file = "emd_30288.map.gz"
        pdb_file = "7c4u.pdb"

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

    def on_stop(self):
        self.temp_dir.cleanup()

    @async_callback
    async def on_run(self):
        # await self.load_map_and_model()
        complexes = await self.request_complex_list()
        self.menu.render(complexes, force_enable=True)

    def enable_search_menu(self):
        self.search_menu.render(force_enable=True)

    async def add_file_to_group(self, filepath):
        path, ext = os.path.splitext(filepath)
        group = next(iter(self.groups.values()), None)
        if ext == ".pdb":
            # For now just add maps to first group
            # Will need to be fixed later
            if group:
                group.add_pdb(filepath)
            self.send_files_to_load([filepath])
            time.sleep(1)  # Give time for PDB to load
            shallow_comp = (await self.request_complex_list())[0]
            comp = (await self.request_complexes([shallow_comp.index]))[0]
            if group:
                group.add_nanome_complex(comp)
                group.generate_mesh()
                group.mesh.upload()

        else:  # Import map.gz
            group_name = os.path.basename(path)
            group = MapGroup(group_name=group_name)
            group.add_map_gz(filepath)
            self.groups[group_name] = group

            # Check if theres a complex we can align to
            group.add_map_gz(filepath)
            complexes = await self.request_complex_list()
            if complexes:
                comp = complexes[0]
                deep_comp = (await self.request_complexes([comp.index]))[0]
                group.add_nanome_complex(deep_comp)
                self.menu.render(complexes)
            if not group:
                group_name = os.path.basename(path)
                group = MapGroup(group_name=group_name)
                self.groups.append(group)
            await self.render_mesh(group)

    async def render_mesh(self, map_group: MapGroup):
        self.set_plugin_list_button(enums.PluginListButtonType.run, "Running...", False)
        Logs.message(f"Generating iso-surface for iso-value {round(map_group.isovalue, 3)}")
        mesh = map_group.generate_mesh()
        Logs.message(f"Uploading iso-surface ({len(mesh.vertices)} vertices)")
        await mesh.upload()
        Logs.message("Uploading completed")
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
