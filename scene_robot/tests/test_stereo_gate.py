import numpy as np
from p2.fusion.stereo import sync_weight,Stereo


def test_sync_gate():
    assert sync_weight(3)==1 and 0<sync_weight(10)<1
    assert sync_weight(15)==0 and sync_weight(50)==0 and sync_weight(100)==0


def test_sgbm_known_disparity():
    rng=np.random.default_rng(4);left=rng.integers(0,255,(200,320,3),np.uint8)
    right=np.zeros_like(left);right[:,:-12]=left[:,12:]
    depth,confidence,meta=Stereo(200).compute(left,right,0)
    valid=(confidence>.4)&(depth>0)
    assert valid.sum()>1000
    assert abs(float(np.median(depth[valid]))-1)<.1
