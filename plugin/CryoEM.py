import nanome
from nanome.api.ui import Menu
from nanome.util import Logs, enums
from nanome.api.shapes import Shape, Mesh
import mrcfile
import gzip
import mcubes
import numpy as np
import pyfqmr
import json
import requests
import tempfile

class CryoEM(nanome.PluginInstance):
    def start(self):
        self.menu = Menu()
        self.menu.title = 'Cryo-EM'
        self.menu.width = 1
        self.menu.height = 1

        self.map_file = None
        self._map_data = None
        self.nanome_mesh = None
        self.iso_value = 0.0
        self.opacity = 0.5
        self._slider_iso = None
        self._slider_opacity = None
        

        # node_input = self.menu.root.create_child_node()
        # text_input = node_input.add_new_text_input("PDBId")


        node_label = self.menu.root.create_child_node()
        self.label_iso = node_label.add_new_label("Iso-value: " + str(round(self.iso_value, 3)))

        iso_node = self.menu.root.create_child_node()
        self._slider_iso = iso_node.add_new_slider(-1.0, 1.0, self.iso_value)


        node_label_opac = self.menu.root.create_child_node()
        self.label_opac = node_label_opac.add_new_label("Opacity: " + str(round(self.opacity, 2)))

        opac_node = self.menu.root.create_child_node()
        self._slider_opacity = opac_node.add_new_slider(0.01, 1.0, self.opacity)

        def download_CryoEM_map(text_in):
            base = "https://data.rcsb.org/rest/v1/core/entry/"
            rest_url = base + text_in.input_text
            response = requests.get(rest_url)
            result = response.json()
            emdb_ids = result["rcsb_entry_container_identifiers"]["emdb_ids"]
            first_emdb = emdb_ids[0]

            new_url = "https://files.rcsb.org/pub/emdb/structures/" + first_emdb + "/map/" + first_emdb.lower().replace("-", "_") + ".map.gz"

            #Write the map to a .map file
            with requests.get(new_url, stream=True) as r:
                r.raise_for_status()
                map_tempfile = tempfile.NamedTemporaryFile(delete=False, suffix='.map.gz')
                with open(local_filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192): 
                        f.write(chunk)
                self.map_file = map_tempfile

        # text_input.register_submitted_callback(download_CryoEM_map)
        self._slider_iso.register_released_callback(self.update_isosurface)
        self._slider_opacity.register_released_callback(self.update_opacity)

    def on_run(self):
        self.menu.enabled = True
        self.update_menu(self.menu)

        self.set_plugin_list_button(enums.PluginListButtonType.run, 'Running...', False)
        
        Logs.message("Reading cryo-em file")

        #6CL7 = 7490
        #Load cryo-em map
        with mrcfile.open('emd_7490.map') as mrc:
            self._map_data = mrc.data
            self.generate_isosurface(0.1)
    
    def update_isosurface(self, iso):
        self.generate_isosurface(iso.current_value)
        self.label_iso.text = "Iso-value: " + str(round(iso.current_value, 3))

    def update_opacity(self, alpha):
        self.opacity = alpha.current_value
        self.label_opac.text = "Opacity: " + str(round(self.opacity, 2))
        if self.nanome_mesh:
            # self.nanome_mesh.color = nanome.util.Color(255, 255, 255, 128)
            self.nanome_mesh.color.a = int(self.opacity * 255)
            self.nanome_mesh.upload()

    def generate_isosurface(self, iso, decimation_factor=10):
        Logs.message("Generating iso-surface for iso-value "+str(iso))
        self.iso_value = iso

        self.set_plugin_list_button(enums.PluginListButtonType.run, 'Running...', False)


        #Compute iso-surface with marching cubes algorithm
        vertices, triangles = mcubes.marching_cubes(self._map_data, iso)

        target = max(100, len(triangles)/decimation_factor)

        mesh_simplifier = pyfqmr.Simplify()
        mesh_simplifier.setMesh(np.asarray(vertices), np.asarray(triangles))
        mesh_simplifier.simplify_mesh(target_count=target, aggressiveness=7, preserve_border=True)

        vertices, triangles, normals = mesh_simplifier.getMesh()

        if self.nanome_mesh is not None:
            self.nanome_mesh.destroy()
        
        self.nanome_mesh = Mesh()

        self.nanome_mesh.vertices = np.asarray(vertices).flatten()
        self.nanome_mesh.normals = np.asarray(normals).flatten()
        self.nanome_mesh.triangles = np.asarray(triangles).flatten()

        self.nanome_mesh.anchors[0].anchor_type = nanome.util.enums.ShapeAnchorType.Workspace
        
        self.nanome_mesh.color = nanome.util.Color(255, 255, 255, 128)

        Logs.message("Uploading iso-surface ("+str(len(self.nanome_mesh.vertices))+" vertices)")
        self.nanome_mesh.upload(self.done_updating)

    def done_updating(self, m):
        Logs.message("Done updating mesh for iso-value "+str(self.iso_value))
        self.set_plugin_list_button(enums.PluginListButtonType.run, 'Run', True)

def main():
    plugin = nanome.Plugin('Cryo-EM', 'Nanome plugin to load Cryo-EM maps and display them in Nanome as surfaces', 'other', False)
    plugin.set_plugin_class(CryoEM)
    plugin.run()


if __name__ == '__main__':
    main()
