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

# from .old_menu import OldMenu
from .menu import MainMenu, EmbiDBMenu
from .models import MapGroup
from .VaultManager import VaultManager

API_KEY = os.environ.get('API_KEY', None)
SERVER_URL = os.environ.get('SERVER_URL', None)


class CryoEM(nanome.AsyncPluginInstance):

    @async_callback
    async def start(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.menu = MainMenu(self)
        self.embi_db_menu = EmbiDBMenu(self)
        self.groups = {}

    def on_stop(self):
        self.temp_dir.cleanup()

    @async_callback
    async def on_run(self):
        self.menu.render(force_enable=True)

    def enable_embi_db_menu(self):
        self.embi_db_menu.render(force_enable=True)

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
            group = next(iter(self.groups.values()))
            group.add_file(filepath)
            await self.render_mesh(group)
        self.menu.render()

    async def render_mesh(self, map_group):
        self.set_plugin_list_button(enums.PluginListButtonType.run, "Running...", False)
        iso = map_group.isovalue
        opacity = map_group.opacity
        color_scheme = map_group.color_scheme

        comps = await self.request_complex_list()
        deep_comp = await self.request_complexes([comps[0].index])
        map_group.nanome_complex = deep_comp[0]
        Logs.message(f"Generating iso-surface for iso-value {str(round(iso, 3))}")
        mesh = map_group.generate_mesh(iso, color_scheme, opacity)
        Logs.message(
            "Uploading iso-surface ("
            + str(len(mesh.vertices))
            + " vertices)"
        )
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
