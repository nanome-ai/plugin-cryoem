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
        self.menu.width = 0.7
        self.menu.height = 1

        self.map_file = None
        self._map_data = None
        self.nanome_mesh = None
        self.iso_value = 0.0
        self.opacity = 0.5
        self._slider_iso = None
        self._slider_opacity = None
        self.limit_x = 0.0
        self.limit_y = 0.0
        self.limit_z = 0.0
        self.limited_view_pos = [0, 0, 0]
        self.limited_view_range = 30.0
        self.current_mesh = []
        
        node_input = self.menu.root.create_child_node()
        text_input = node_input.add_new_text_input("PDBId")
        node_input.set_size_ratio(0.05)

        node_label = self.menu.root.create_child_node()
        self.label_iso = node_label.add_new_label("Iso-value: " + str(round(self.iso_value, 3)))
        node_label.set_size_ratio(0.05)

        node_iso = self.menu.root.create_child_node()
        self._slider_iso = node_iso.add_new_slider(-1.0, 1.0, self.iso_value)
        node_iso.set_size_ratio(0.05)

        node_label_opac = self.menu.root.create_child_node()
        self.label_opac = node_label_opac.add_new_label("Opacity: " + str(round(self.opacity, 2)))
        node_label_opac.set_size_ratio(0.01)

        opac_node = self.menu.root.create_child_node()
        self._slider_opacity = opac_node.add_new_slider(0.01, 1.0, self.opacity)
        opac_node.set_size_ratio(0.05)

        node_label_limit_x = self.menu.root.create_child_node()
        self.label_limit_x = node_label_limit_x.add_new_label("Position.x: " + str(round(self.limit_x, 2)))
        node_label_limit_x.set_size_ratio(0.01)

        limit_x_node = self.menu.root.create_child_node()
        self._slider_limit_x = limit_x_node.add_new_slider(-50, 50, self.limit_x)
        limit_x_node.set_size_ratio(0.05)

        node_label_limit_y = self.menu.root.create_child_node()
        self.label_limit_y = node_label_limit_y.add_new_label("Position.y: " + str(round(self.limit_y, 2)))
        node_label_limit_y.set_size_ratio(0.01)

        limit_y_node = self.menu.root.create_child_node()
        self._slider_limit_y = limit_y_node.add_new_slider(-50, 50, self.limit_y)
        limit_y_node.set_size_ratio(0.05)

        node_label_limit_z = self.menu.root.create_child_node()
        self.label_limit_z = node_label_limit_z.add_new_label("Position.z: " + str(round(self.limit_z, 2)))
        node_label_limit_z.set_size_ratio(0.01)

        limit_z_node = self.menu.root.create_child_node()
        self._slider_limit_z = limit_z_node.add_new_slider(-50, 50, self.limit_z)
        limit_z_node.set_size_ratio(0.05)

        node_label_limit_range = self.menu.root.create_child_node()
        self.label_limit_range = node_label_limit_range.add_new_label("Size: " + str(round(self.limited_view_range, 2)))
        node_label_limit_range.set_size_ratio(0.01)

        limit_range_node = self.menu.root.create_child_node()
        self._slider_limit_range = limit_range_node.add_new_slider(0, 150, self.limited_view_range)
        limit_range_node.set_size_ratio(0.05)


        def download_CryoEM_map(text_in):
            Logs.message("Downloading PDB info for ID:",text_in.input_text)
            self.send_notification(nanome.util.enums.NotificationTypes.message, "Downloading EM data")
            base = "https://data.rcsb.org/rest/v1/core/entry/"
            rest_url = base + text_in.input_text
            response = requests.get(rest_url)
            result = response.json()
            emdb_ids = result["rcsb_entry_container_identifiers"]["emdb_ids"]
            if len(emdb_ids) >= 1:
                first_emdb = emdb_ids[0]
                Logs.message("Downloading EM data for EMDBID:", first_emdb)

                new_url = "https://files.rcsb.org/pub/emdb/structures/" + first_emdb + "/map/" + first_emdb.lower().replace("-", "_") + ".map.gz"

                #Write the map to a .map file
                with requests.get(new_url, stream=True) as r:
                    r.raise_for_status()
                    map_tempfile = tempfile.NamedTemporaryFile(delete=False, suffix='.map.gz')
                    with open(map_tempfile.name, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192): 
                            f.write(chunk)
                    self.map_file = map_tempfile
                    self.load_map()
                    self.generate_isosurface(0.1)
            else:
                Logs.message("No EM data found for", text_in.input_text)
                

        text_input.register_submitted_callback(download_CryoEM_map)
        self._slider_iso.register_released_callback(self.update_isosurface)
        self._slider_opacity.register_released_callback(self.update_opacity)
        self._slider_limit_x.register_released_callback(self.update_limited_view_x)
        self._slider_limit_y.register_released_callback(self.update_limited_view_y)
        self._slider_limit_z.register_released_callback(self.update_limited_view_z)
        self._slider_limit_range.register_released_callback(self.update_limited_view_range)

    def load_map(self):
        with mrcfile.open(self.map_file.name) as mrc:
            self._map_data = mrc.data
    
    def on_run(self):
        self.menu.enabled = True
        self.update_menu(self.menu)

    def update_isosurface(self, iso):
        self.label_iso.text = "Iso-value: " + str(round(iso.current_value, 3))
        self.update_content(self.label_iso)
        if self._map_data is not None:
            self.generate_isosurface(iso.current_value)
        
    def update_limited_view_x(self, slider):
        self.limit_x = slider.current_value
        self.limited_view_pos = [self.limit_x, self.limit_y, self.limit_z]
        self.update_mesh_limited_view()

    def update_limited_view_y(self, slider):
        self.limit_y = slider.current_value
        self.limited_view_pos = [self.limit_x, self.limit_y, self.limit_z]
        self.update_mesh_limited_view()

    def update_limited_view_z(self, slider):
        self.limit_z = slider.current_value
        self.limited_view_pos = [self.limit_x, self.limit_y, self.limit_z]
        self.update_mesh_limited_view()
    
    def update_limited_view_range(self, slider):
        self.limited_view_range = slider.current_value
        self.update_mesh_limited_view()

    def update_mesh_limited_view(self):
        if self.current_mesh != [] and self.nanome_mesh is not None:
            vertices, normals, triangles  = self.limit_view(self.current_mesh, self.limited_view_pos, self.limited_view_range)

            self.nanome_mesh.vertices = np.asarray(vertices).flatten()
            self.nanome_mesh.normals = np.asarray(normals).flatten()
            self.nanome_mesh.triangles = np.asarray(triangles).flatten()

            self.nanome_mesh.upload()

    def update_opacity(self, alpha):

        self.opacity = alpha.current_value
        self.label_opac.text = "Opacity: " + str(round(self.opacity, 2))
        self.update_content(self.label_opac)

        if self._map_data is not None and self.nanome_mesh:
            self.nanome_mesh.color.a = int(self.opacity * 255)
            self.nanome_mesh.upload()
            Logs.debug("Setting opacity to", int(self.opacity * 255))

    def limit_view(self, mesh, position, range):
        vertices, normals, triangles = mesh

        print("---- verts: ",vertices)
        print("---- tris: ",triangles)
        print("---- norms: ",normals)
        pos = np.asarray(position)
        idv = 0
        to_keep = []
        for v in vertices:
            vert = np.asarray(v)
            dist = np.linalg.norm(vert - pos)
            if dist <= range:
                to_keep.append(idv)
            idv+=1
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
            idv+=1

        for t in triangles:
            if mapping[t[0]] != -1 and mapping[t[1]] != -1 and mapping[t[2]] != -1:
                new_triangles.append([mapping[t[0]], mapping[t[1]], mapping[t[2]]])
        
        return (np.asarray(new_vertices), np.asarray(new_normals), np.asarray(new_triangles))

    def generate_isosurface(self, iso, decimation_factor=5):
        Logs.message("Generating iso-surface for iso-value "+str(round(iso, 3)))
        self.iso_value = iso

        self.set_plugin_list_button(enums.PluginListButtonType.run, 'Running...', False)

        #Compute iso-surface with marching cubes algorithm
        vertices, triangles = mcubes.marching_cubes(self._map_data, iso)

        target = max(100, len(triangles)/decimation_factor)

        mesh_simplifier = pyfqmr.Simplify()
        mesh_simplifier.setMesh(np.asarray(vertices), np.asarray(triangles))
        mesh_simplifier.simplify_mesh(target_count=target, aggressiveness=7, preserve_border=True)

        vertices, triangles, normals = mesh_simplifier.getMesh()

        self.current_mesh = [vertices, normals, triangles]
        
        vertices, normals, triangles = self.limit_view((vertices, normals, triangles), self.limited_view_pos, self.limited_view_range)

        if self.nanome_mesh is None:
            self.nanome_mesh = Mesh()

        self.nanome_mesh.vertices = np.asarray(vertices).flatten()
        self.nanome_mesh.normals = np.asarray(normals).flatten()
        self.nanome_mesh.triangles = np.asarray(triangles).flatten()

        self.nanome_mesh.anchors[0].anchor_type = nanome.util.enums.ShapeAnchorType.Workspace
        
        self.nanome_mesh.color = nanome.util.Color(255, 255, 255, int(self.opacity * 255))

        Logs.message("Uploading iso-surface ("+str(len(self.nanome_mesh.vertices))+" vertices)")
        self.nanome_mesh.upload(self.done_updating)

    def done_updating(self, m):
        Logs.message("Done updating mesh for iso-value "+str(round(self.iso_value, 3)))
        self.set_plugin_list_button(enums.PluginListButtonType.run, 'Run', True)

def main():
    plugin = nanome.Plugin('Cryo-EM', 'Nanome plugin to load Cryo-EM maps and display them in Nanome as surfaces', 'other', False)
    plugin.set_plugin_class(CryoEM)
    plugin.run()


if __name__ == '__main__':
    main()
