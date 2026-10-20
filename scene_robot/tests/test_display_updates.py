from types import SimpleNamespace
import time
import numpy as np
from p2.ui.display_updates import voxel_buffer,MarkerNodes,MarkerWorker


def test_voxel_buffer_exactly_matches_installed_viser_encoder():
    import viser
    rng=np.random.default_rng(42);points=rng.random((30,3));colors=rng.integers(0,256,(30,3),dtype=np.uint8);size=.008
    server=viser.ViserServer(host='127.0.0.1',port=8090,verbose=False)
    try:
        handle=server.scene.add_gaussian_splats('/test',points,np.broadcast_to(np.eye(3,dtype=np.float32)*size**2,(30,3,3)),colors.astype(np.float32)/255,np.full((30,1),.85,np.float32))
        assert np.array_equal(handle.buffer,voxel_buffer(points,colors,size))
        padded=voxel_buffer(points,colors,size,8192)
        assert np.array_equal(handle.buffer,padded[:len(points)])
        assert not padded[len(points):,7].any()
        assert np.isfinite(padded[:,:3].copy().view(np.float32)).all()
        assert np.all(padded[:,4:7]==padded[0,4:7])
    finally:server.stop()


def test_marker_nodes_retain_nodes_and_change_only_bounds():
    made=[];removed=[]
    class Scene:
        def add_line_segments(self,*args,**kwargs):
            h=SimpleNamespace(visible=True,points=args[1],remove=lambda:removed.append('line'));made.append(h);return h
        def add_label(self,*args,**kwargs):
            h=SimpleNamespace(visible=True,position=kwargs['position'],remove=lambda:removed.append('label'));made.append(h);return h
    scene=Scene();nodes=MarkerNodes();row={'kind':'new','label':'NEW since scan','bounds':[[0,0,0],[1,1,1]]}
    nodes.update(scene,[row],True,1.15);points=made[0].points
    nodes.update(scene,[row],False,1.15)
    assert len(made)==2 and made[0].points is points and not made[1].visible
    nodes.update(scene,[{**row,'bounds':[[0,0,0],[2,1,1]]}],True,1.15)
    assert len(made)==2 and made[0].points is not points and made[1].visible
    nodes.update(scene,[{**row,'bounds':[[0,0,0],[2,1,1]]}],True,.65)
    assert made[1].font_screen_scale==.65 and len(made)==2
    nodes.update(scene,[],True,1.15);assert removed==['label','line']


def test_marker_worker_copies_input_and_bounds_inflight_jobs():
    import threading
    release=threading.Event()
    class Detector:
        def update(self,points,trace):
            release.wait(2);return [points.tolist(),trace]
    worker=MarkerWorker(Detector());points=np.array([1]);trace=[{'clear':False}]
    try:
        assert worker.submit(points,trace)
        assert not worker.submit(points,trace)
        points[0]=9;trace[0]['clear']=True;release.set()
        result=None
        for _ in range(100):
            result=worker.poll()
            if result is not None:break
            time.sleep(.01)
        assert result[0]==[[1],[{'clear':False}]]
    finally:worker.close()
