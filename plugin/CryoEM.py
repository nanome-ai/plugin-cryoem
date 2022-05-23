from lib2to3.pgen2.pgen import generate_grammar
import nanome
from nanome.api.ui import Menu
from nanome.util import Logs, enums
from nanome.api.shapes import Shape, Mesh
import mrcfile
import mcubes
import numpy as np
import pyfqmr

class CryoEM(nanome.PluginInstance):
    def start(self):
        self.menu = Menu()
        self.menu.title = 'Cryo-EM'
        self.menu.width = 1
        self.menu.height = 1

        self._map_data = None
        self.nanome_mesh = None
        self.iso_value = 0.0

        msg = 'Cryo-EM'
        node = self.menu.root.create_child_node()
        node.add_new_label(msg)

    def on_run(self):
        self.menu.enabled = True
        self.update_menu(self.menu)

        self.set_plugin_list_button(enums.PluginListButtonType.run, 'Running...', False)
        
        Logs.message("Reading cryo-em file")

        #6CL7 = 7490
        #Load cryo-em map
        with mrcfile.open('emd_7490.map') as mrc:
            self._map_data = mrc.data
            self.generate_isosurface(0.32)
    
    def generate_isosurface(self, iso, decimation_factor=10):
        Logs.message("Generating iso-surface for iso-value "+str(iso))
        self.iso_value = iso

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
