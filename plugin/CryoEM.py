import os
import tempfile
from pathlib import Path

from nanome.util import Logs, enums
from nanome.api import structure
from .menu import MainMenu
from .models import MapGroup
from .vault_manager import VaultManager
from .vault_menu import VaultMenu

from nanome.beta.nanome_sdk import NanomePlugin

import logging
logging.getLogger('matplotlib').setLevel(logging.WARNING)


class CryoEM(NanomePlugin):

    def __init__(self):
        super().__init__()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.menu = MainMenu(self)
        self.groups = []
        self.add_mapgroup()
        self.vault_url = os.environ.get("VAULT_URL")
        self.vault_api_key = os.environ.get("VAULT_API_KEY")

    async def on_stop(self):
        self.temp_dir.cleanup()

    async def on_run(self):
        await self.menu.render(force_enable=True)
        presenter_info = await self.client.request_presenter_info()
        org = f'org-{presenter_info.org_id}'
        user_id = presenter_info.account_id
        self.vault_manager = VaultManager(self.vault_api_key, self.vault_url)
        self.vault_menu = VaultMenu(self, self.vault_manager, org, user_id)
        self.vault_menu.create_menu()

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

    async def add_model_to_group(self, filepath):
        # Look for a MapGroup to add the model to
        selected_mapgroup_name = self.menu.get_selected_mapgroup()
        mapgroup = self.get_group(selected_mapgroup_name)
        if not mapgroup:
            if not self.groups:
                self.add_mapgroup()
                mapgroup = self.groups[0]
            else:
                self.client.send_notification(enums.NotificationTypes.error, "Please select a MapGroup.")
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

        [created_comp] = await self.client.add_to_workspace([model_comp])
        if mapgroup:
            mapgroup.add_model_complex(created_comp)

    async def create_model_complex(self, model_filepath: str):
        model_path = Path(model_filepath)
        suffix = model_path.suffix
        if suffix == ".pdb":
            comp = structure.Complex.io.from_pdb(path=model_filepath)
        elif suffix == '.sdf':
            comp = structure.Complex.io.from_sdf(path=model_filepath)
        elif suffix in ['.cif', 'mmcif']:
            comp = structure.Complex.io.from_mmcif(path=model_filepath)

        # Get new complex, and associate to MapGroup
        comp.name = Path(model_filepath).stem
        self.client.add_bonds([comp])
        self.remove_hydrogens(comp)
        comp.locked = True
        return comp

    async def add_mapfile_to_group(self, map_gz_filepath, isovalue=None, metadata=None):
        selected_mapgroup_name = self.menu.get_selected_mapgroup()
        mapgroup = self.get_group(selected_mapgroup_name)
        if not mapgroup:
            if not self.groups:
                self.add_mapgroup()
                mapgroup = self.groups[0]
            else:
                self.client.send_notification(enums.NotificationTypes.error, "Please select a MapGroup.")
                return
        if isovalue:
            Logs.debug(f"Setting isovalue to {isovalue}")
            mapgroup.isovalue = isovalue
        mapgroup.metadata = metadata
        await mapgroup.add_mapfile(map_gz_filepath)
        if mapgroup.model_complex:
            # Get latest position of model complex
            [deep_comp] = await self.client.request_complexes([mapgroup.model_complex.index])
            if not deep_comp:
                Logs.warning("model complex was deleted.")
            else:
                mapgroup.add_model_complex(deep_comp)
        await mapgroup.generate_full_mesh()
        # Rename Mapgroup after the new map
        mapgroup.group_name = Path(map_gz_filepath).stem
        await self.menu.render(selected_mapgroup=mapgroup)

    async def delete_mapgroup(self, map_group: MapGroup, current_comp_indices=None):
        if not current_comp_indices:
            current_comp_list = await self.client.request_complex_list()
            current_comp_indices = [comp.index for comp in current_comp_list]
        map_comp = map_group.map_mesh.complex
        model_comp = map_group.model_complex
        comps_to_delete = []
        # Only try to delete comp if the index is in the current_comp_indices
        # Otherwise, a new entry named 'complex' is added to the workspace.
        if map_comp and map_comp.index in current_comp_indices:
            comps_to_delete.append(map_comp)
        if model_comp and model_comp.index in current_comp_indices:
            comps_to_delete.append(model_comp)
        if comps_to_delete:
            await self.client.remove_from_workspace(comps_to_delete)
        try:
            self.groups.remove(map_group)
        except ValueError:
            Logs.warning("Tried to delete a map group that doesn't exist.")

        # Delete map file if it exists.
        if map_group.mapfile and os.path.exists(map_group.mapfile):
            os.remove(map_group.mapfile)
        selected_mapgroup_name = self.menu.get_selected_mapgroup()
        mapgroup = self.get_group(selected_mapgroup_name)
        await self.menu.render(selected_mapgroup=mapgroup)

    @staticmethod
    def remove_hydrogens(comp):
        """Remove hydrogen atoms from the complex."""
        for atom in [atm for atm in comp.atoms if atm.symbol == 'H']:
            residue = atom.residue
            residue.remove_atom(atom)
            for bond in atom.bonds:
                residue.remove_bond(bond)

    @property
    def request_futs(self):
        return self.client.request_futs

    async def on_complex_added_removed(self):
        # Check each mapgroup and delete any where the complex was deleted.
        comp_list = await self.client.request_complex_list()
        comp_indices = [cmp.index for cmp in comp_list]
        for mapgroup in self.groups:
            has_model = bool(mapgroup.model_complex) and mapgroup.model_complex.index in comp_indices
            has_map = mapgroup.map_complex and mapgroup.map_complex.index in comp_indices
            if not has_model and not has_map:
                await self.delete_mapgroup(mapgroup, comp_indices)
                # Close menu if it's open
                for menu in self.ui_manager._menus:
                    if menu.title.startswith(mapgroup.group_name):
                        menu.enabled = False
                        self.client.update_menu(menu)
