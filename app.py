from plugin.models import MapGroup, MapMesh
from fastapi import FastAPI, UploadFile, Header, File
import tempfile

app = FastAPI()


@app.post('/upload')
async def upload_file(file: UploadFile = File(...), room_id: str = Header(...)):
    filename = file.filename
    print(f"Room Code: {room_id}")
    print(f"Filename: {filename}")
    isovalue = 0.2
    # opacity = 0.65
    breakpoint()
    with tempfile.NamedTemporaryFile(suffix='.map.gz') as map_gz_file:
        plugin = None  # we don't actually need a connected plugin for what we're doing
        mg = MapGroup(plugin)
        map_gz_file.write(await file.read())
        await mg.add_map_gz(map_gz_file.name)
        map_mgr = mg.map_mesh.map_manager
    mesh = MapMesh.generate_mesh_from_map_manager(map_mgr, isovalue)
    return 'File uploaded successfully'

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app)
