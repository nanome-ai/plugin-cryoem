import mrcfile
import matplotlib.pyplot as plt
import numpy as np
import tempfile


class MapGroup:

    def __init__(self, **kwargs):
        self.group_name = kwargs.get("group_name", "")
        self.files = kwargs.get("files", [])
        self.mesh = None
        self._map_data = None
        self._map_voxel_size = None
        self._map_origin = None

    def add_file(self, filepath: str):
        self.files.append(filepath)
        if not filepath.endswith('pdb'):
            self.load_map(filepath)

    def load_map(self, map_filepath: str):
        with mrcfile.open(map_filepath) as mrc:
            self._map_data = mrc.data
            h = mrc.header
            self._map_voxel_size = mrc.voxel_size
            axes_order = np.hstack([h.mapc, h.mapr, h.maps])
            transpose_order = np.argsort(axes_order[::-1])
            self._map_data = np.transpose(self._map_data, axes=transpose_order)

            voxel_sizes = [self._map_voxel_size.x, self._map_voxel_size.y, self._map_voxel_size.z]
            delta = np.diag(np.array(voxel_sizes))
            
            axes_c_order = np.argsort(axes_order)
            nstarts = [h.nxstart, h.nystart, h.nzstart]
            offsets = np.hstack(nstarts)[axes_c_order] * np.diag(delta)
            
            origin_coords = [h.origin.x, h.origin.y, h.origin.z]
            self._map_origin = np.hstack(origin_coords) + offsets

    def generate_histogram(self, temp_dir: str):
        flat = self._map_data.flatten()
        minmap = np.min(flat)
        flat_offset = flat + abs(minmap) + 0.001
        hist, bins = np.histogram(flat_offset, bins=1000)
        logbins = np.logspace(np.log10(bins[0]), np.log10(bins[-1]), len(bins))
        plt.hist(flat, bins=logbins - abs(minmap))
        plt.ylim(bottom=10)
        plt.yscale('log')
        plt.title("Level histogram")
        self.png_tempfile = tempfile.NamedTemporaryFile(
            delete=False, suffix=".png", dir=temp_dir)
        plt.savefig(self.png_tempfile.name)
        return self.png_tempfile.name
