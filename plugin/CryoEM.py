import os
import tempfile
from pathlib import Path

import nanome
from nanome.util import Logs, enums, async_callback
from nanome.api import structure
from . import __version__
from .menu import MainMenu
from .models import MapGroup
from .session_client import SessionClient


class CryoEM(nanome.AsyncPluginInstance):

    async def on_start(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.menu = MainMenu(self)
        self.groups = []
        self.client = SessionClient(self.plugin_id, self.session_id, self.version_table)
        self.add_mapgroup()
        await self.client.connect_stdin_stdout()

    def on_stop(self):
        self.temp_dir.cleanup()

    @async_callback
    async def on_run(self):
        self.menu.render(force_enable=True)

    def add_mapgroup(self):
        group_num = 1
        existing_group_names = [group.group_name for group in self.groups]
        while True:
            group_name = f'MapGroup {group_num}'
            if group_name not in existing_group_names:
                map_group = MapGroup(self, group_name=group_name)
                break
            group_num += 1
        self.groups.append(map_group)

    def get_group(self, group_name):
        return next((
            group for group in self.groups
            if group.group_name == group_name
        ), None)

    async def add_pdb_to_group(self, filepath):
        # Look for a MapGroup to add the model to
        selected_mapgroup_name = self.menu.get_selected_mapgroup()
        mapgroup = self.get_group(selected_mapgroup_name)
        if not mapgroup:
            if not self.groups:
                self.add_mapgroup()
                mapgroup = self.groups[0]
            else:
                self.send_notification(enums.NotificationTypes.error, "Please select a MapGroup.")
                return
        model_comp = await self.create_model_complex(filepath)
        if mapgroup:
            mapgroup.add_pdb(filepath)
            model_comp.locked = True
            model_comp.boxed = False
            map_complex = mapgroup.map_complex
            if map_complex:
                model_comp.position = map_complex.position
                model_comp.rotation = map_complex.rotation

        [created_comp] = await self.add_to_workspace([model_comp])
        if mapgroup:
            mapgroup.add_model_complex(created_comp)

    async def create_model_complex(self, pdb_filepath: str):
        comp = structure.Complex.io.from_pdb(path=pdb_filepath)
        # Get new complex, and associate to MapGroup
        comp.name = Path(pdb_filepath).stem
        await self.add_bonds([comp])
        self.remove_hydrogens(comp)
        comp.locked = True
        return comp

    async def add_mapgz_to_group(self, map_gz_filepath, isovalue=None, metadata=None):
        selected_mapgroup_name = self.menu.get_selected_mapgroup()
        mapgroup = self.get_group(selected_mapgroup_name)
        if not mapgroup:
            if not self.groups:
                self.add_mapgroup()
                mapgroup = self.groups[0]
            else:
                self.send_notification(enums.NotificationTypes.error, "Please select a MapGroup.")
                return
        if isovalue:
            Logs.debug(f"Setting isovalue to {isovalue}")
            mapgroup.isovalue = isovalue
        mapgroup.metadata = metadata
        await mapgroup.add_map_gz(map_gz_filepath)
        if mapgroup.model_complex:
            # Get latest position of model complex
            [deep_comp] = await self.request_complexes([mapgroup.model_complex.index])
            if not deep_comp:
                Logs.warning("model complex was deleted.")
            else:
                mapgroup.add_model_complex(deep_comp)
        await mapgroup.generate_full_mesh()
        # Rename Mapgroup after the new map
        mapgroup.group_name = Path(map_gz_filepath).stem
        self.menu.render(selected_mapgroup=mapgroup)

    async def delete_mapgroup(self, map_group: MapGroup):
        map_comp = map_group.map_mesh.complex
        model_comp = map_group.model_complex
        comps_to_delete = []
        if map_comp:
            comps_to_delete.append(map_comp)
        if model_comp:
            comps_to_delete.append(model_comp)
        if comps_to_delete:
            await self.remove_from_workspace(comps_to_delete)
        try:
            self.groups.remove(map_group)
        except ValueError:
            Logs.warning("Tried to delete a map group that doesn't exist.")

        # Delete map file if it exists.
        if map_group.map_gz_file:
            os.remove(map_group.map_gz_file)
        selected_mapgroup_name = self.menu.get_selected_mapgroup()
        mapgroup = self.get_group(selected_mapgroup_name)
        self.menu.render(selected_mapgroup=mapgroup)

    @staticmethod
    def remove_hydrogens(comp):
        """Remove hydrogen atoms from the complex."""
        for atom in [atm for atm in comp.atoms if atm.symbol == 'H']:
            residue = atom.residue
            residue.remove_atom(atom)
            for bond in atom.bonds:
                residue.remove_bond(bond)
