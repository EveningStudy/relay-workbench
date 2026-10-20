"""Display samples are bounded observations, not voxel-centre densification."""
from pathlib import Path
from unittest.mock import patch
import numpy as np
from p2.msgs import CameraFrame,DisplayEvidence,encode,decode
from p2.ui.live_points import RecentLivePoints


def layer(**overrides):
    cfg=dict(window_s=.75,pixel_stride=1,points_per_frame=100,frames_per_camera=3,point_budget=12,update_hz=10)
    cfg.update(overrides)
    return RecentLivePoints(cfg,dict(resolution_m=.02,workspace_min=[-1,-1,0],workspace_max=[1,1,2],max_range_m=3.5))


def observation(cam='head_left',seq=1,t=1_000_000_000):
    rgb=np.arange(4*4*3,dtype=np.uint8).reshape(4,4,3)
    frame=CameraFrame(cam,seq,t,t,'synthetic','pinhole',4,4,rgb,np.ones((4,4),np.float32),'sim_ideal')
    y,x=np.mgrid[:4,:4];rays=np.stack([x*.004+.001,y*.004+.001,np.ones_like(x)],-1).astype(np.float32)
    return frame,rays


def test_actual_pixels_live_gate_budget_expiry_and_no_io():
    display=layer();frame,rays=observation();centres=np.array([[.01,.01,1.01]])
    with patch('builtins.open',side_effect=AssertionError('unexpected file access')),patch.object(Path,'read_text',side_effect=AssertionError('unexpected file access')):
        display.accept(frame,np.eye(4),rays,None,1)
        empty,_=display.select(frame.t_capture_ns,np.empty((0,3)),.12)
        assert len(empty.points)==0  # an accepted pixel does not bypass LIVE state
        shown,_=display.select(frame.t_capture_ns+100_000_000,centres,.12)
        assert len(shown.points)==12
        for point,color in zip(shown.points,shown.colors):
            pixel=np.flatnonzero(np.all(rays.reshape(-1,3)==point,axis=1))
            assert len(pixel)==1 and np.array_equal(color,frame.rgb.reshape(-1,3)[pixel[0]])
        assert not np.allclose(shown.points[0],centres[0])
        expired,_=display.select(frame.t_capture_ns+750_000_001,centres,.12)
        assert len(expired.points)==0


def test_revoke_while_upload_throttled_and_fair_cameras():
    display=layer(point_budget=10,update_hz=1);frame,rays=observation()
    other,_=observation('wrist_left')
    display.accept(frame,np.eye(4),rays,None,1);display.accept(other,np.eye(4),rays,None,4)
    shown,_=display.select(frame.t_capture_ns,np.array([[.01,.01,1.01]]),.12)
    assert len(shown.points)==10 and np.sum(shown.sources==1)==5 and np.sum(shown.sources==4)==5
    revoked,due=display.select(frame.t_capture_ns+1,np.empty((0,3)),.12)
    assert not due and not len(revoked.points)  # removal never waits for refresh rate


def test_depth_confidence_pose_and_buffer_contract():
    display=layer(frames_per_camera=2);frame,rays=observation()
    frame.depth_kind='none';display.accept(frame,np.eye(4),rays,None,1);assert not display.buffers
    frame.depth_kind='sgbm';confidence=np.zeros((4,4));confidence[0,0]=.8
    transform=np.eye(4);transform[0,3]=.1
    for seq in range(4):
        frame.seq=seq;frame.t_capture_ns=1_000_000_000+seq*10_000_000
        display.accept(frame,transform,rays,confidence,1)
    assert len(display.buffers['head_left'])==2
    stored=display.buffers['head_left'][-1][1]
    assert len(stored.points)==1 and np.allclose(stored.points[0],rays[0,0]+[.1,0,0])
    frame.t_capture_ns-=100_000_000;display.accept(frame,transform,rays,confidence,1)
    assert len(display.buffers['head_left'])==2


def test_floor_and_future_samples_hidden():
    display=layer();frame,rays=observation();frame.depth[:]=.1
    display.accept(frame,np.eye(4),rays,None,1)
    centres=np.array([[.01,.01,.11]])
    assert len(display.select(frame.t_capture_ns-1,centres,0,True)[0].points)==0
    assert len(display.select(frame.t_capture_ns+100_000_000,centres,.12)[0].points)==0
    assert len(display.select(frame.t_capture_ns+200_000_000,centres,.12,True)[0].points)>0


def test_recent_display_transport_is_optional_and_preserves_ns():
    import msgpack
    t=1792203541742322239;p=np.array([[.123,.456,1.023]],np.float32)
    original=DisplayEvidence(t,1,p,np.array([0],np.int8),p,np.array([False]),np.array([t],np.int64),p,np.array([t-123],np.int64))
    _,copy=decode(encode('fusion/evidence',original))
    assert np.array_equal(copy.live_depth_points,p) and copy.live_depth_capture_ns[0]==t-123
    original.live_depth_points=None;original.live_depth_capture_ns=None
    _,copy=decode(encode('fusion/evidence',original));assert copy.live_depth_points is None
    old=encode('fusion/evidence',original);header=msgpack.unpackb(old[1],raw=False)
    del header['fields']['live_depth_points'];del header['fields']['live_depth_capture_ns']
    old[1]=msgpack.packb(header,use_bin_type=True)
    _,copy=decode(old);assert copy.live_depth_points is None and copy.live_depth_capture_ns is None


def test_display_callback_does_not_change_fusion_state(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import yaml
    import p2.fusion.fusion_node as module
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module,'TransformBuffer',lambda *args:SimpleNamespace(
        pose=lambda *args:(np.eye(4),{'linear_m':0.,'angular_rad':0.})))
    cfg=dict(device='cpu',resolution_m=.02,workspace_min=[-1,-1,0],workspace_max=[1,1,2],
             geometry_cameras=['head_left'],max_age_ms=500,max_range_m=3.5,pose_time='capture',
             timestamp_uncertainty_ms=2,pixel_stride=1,hit_logodds=.85,free_logodds=-.55,
             ray_step_m=.02,free_margin_m=.015,live_seconds=2,live_min_hits=3,live_min_neighbors=2)
    Path('fusion.yaml').write_text(yaml.safe_dump(cfg))
    # A synthetic depth camera avoids invoking the stereo implementation here.
    cameras={'head_left':dict(width=4,height=4,model='pinhole',frame='camera',depth_mode='sim_ideal')}
    display=layer();frame,rays=observation();plain=module.Fusion(cameras,'fusion.yaml','plain.jsonl',clock=lambda:frame.t_capture_ns)
    tapped=module.Fusion(cameras,'fusion.yaml','tapped.jsonl',clock=lambda:frame.t_capture_ns,observation_sink=display.accept)
    before_rgb=frame.rgb.copy();before_depth=frame.depth.copy()
    try:
        for seq in range(1,5):
            frame.seq=seq;frame.t_capture_ns+=10_000_000
            assert plain.integrate(frame,frame.t_capture_ns)['accepted']
            assert tapped.integrate(frame,frame.t_capture_ns)['accepted']
        for name in ('logodds','color','hit_count','free_count','last_hit','last_free','last_seen','source'):
            assert np.array_equal(getattr(plain.map,name).numpy(),getattr(tapped.map,name).numpy()),name
        assert np.array_equal(frame.rgb,before_rgb) and np.array_equal(frame.depth,before_depth)
    finally:plain.log.close();tapped.log.close()
