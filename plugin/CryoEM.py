import os
import tempfile
import nanome
from nanome.api.structure import Complex
from nanome.util import Logs, async_callback, enums
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
        map_file = "emd_30288.map.gz"
        pdb_file = "7c4u.pdb"
        dm = DataManager()
        dm.set_overwrite(True)
        mm = dm.get_real_map(map_file)
        Logs.message("loaded map")
        model = dm.get_model(pdb_file)
        Logs.message("loaded model")
        mmm = map_model_manager(
            model=model,
            map_manager=mm
        )
        selection_string = 'resseq 1:1000'
        box_mmm = mmm.extract_all_maps_around_model(selection_string=selection_string)
        # Write boxed residue range to files
        boxed_map_filename = os.path.join(self.temp_dir.name, os.path.basename(map_file))
        dm.write_real_map_file(
            box_mmm.map_manager(),
            filename=boxed_map_filename)
        boxed_model_filename = os.path.join(self.temp_dir.name, os.path.basename(pdb_file))
        dm.write_model_file(
            box_mmm.model(),
            filename=boxed_model_filename,
            extension="pdb")
        await self.send_files_to_load([boxed_model_filename])

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
        iso = map_group.isovalue
        opacity = map_group.opacity
        color_scheme = map_group.color_scheme

        comps = await self.request_complex_list()
        if comps:
            deep_comp = await self.request_complexes([comps[0].index])
            map_group.nanome_complex = deep_comp[0]
        else:
            map_group.nanome_complex = None
        Logs.message(f"Generating iso-surface for iso-value {round(iso, 3)}")
        mesh = map_group.generate_mesh(iso, color_scheme, opacity)
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
