import numpy as np
from p2.msgs import CameraFrame, encode, decode
from p2.sim.fisheye import CubeRemap, FACE_ROTATIONS, project_kb


def test_frame_roundtrip():
    f=CameraFrame('head_left',1,123,456,'synthetic','pinhole',4,3,np.zeros((3,4,3),np.uint8),np.ones((3,4),np.float32),'sim_ideal')
    _,g=decode(encode('camera/head_left',f))
    assert g.t_capture_ns==123 and np.array_equal(f.depth,g.depth)


def test_kb_cube_projection():
    remap=CubeRemap()
    errors=[]
    for y,x in [(256,256),(80,250),(400,130),(210,470),(180,65)]:
        face=remap.faces[y,x];u,v=[m[y,x] for m in remap.maps[face]]
        cube_ray=np.array([(u-127.5)/128,(v-127.5)/128,1.])
        ray=FACE_ROTATIONS[face]@cube_ray
        errors.append(np.linalg.norm(project_kb(ray)-[x,y]))
    assert max(errors)<0.5
