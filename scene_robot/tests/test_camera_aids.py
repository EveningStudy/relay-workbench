from types import SimpleNamespace
import numpy as np
from p2.ui.camera_aids import update,PALETTE


def test_view_outlines_use_calibration_and_received_capture_pose():
    calls=[];poses=[]
    class Scene:
        def add_camera_frustum(self,name,**kw):calls.append(('head',kw));return SimpleNamespace(visible=True)
        def add_line_segments(self,name,points,color,**kw):calls.append(('wrist',points));return SimpleNamespace(visible=True)
        def add_label(self,*a,**kw):return SimpleNamespace(visible=True,position=kw['position'])
    class TF:
        def pose(self,frame,t):poses.append((frame,t));return np.eye(4),{}
    cfg={name:{'frame':name,'model':'kb4' if 'wrist' in name else 'pinhole','width':640,'height':480,'horizontal_fov_deg':90} for name in PALETTE}
    received={name:(SimpleNamespace(t_capture_ns=123),999) for name in PALETTE}
    handles={};update(SimpleNamespace(scene=Scene()),TF(),received,cfg,handles)
    assert [t for frame,t in poses]==[123]*3
    assert np.isclose(calls[0][1]['fov'],2*np.arctan(.75))
    for kind,points in calls[1:]:
        assert kind=='wrist' and np.isfinite(points).all()
        assert points[:,:,2].min()>=-1e-8
        assert np.allclose(np.linalg.norm(points,axis=-1),.22)
    assert set(handles)==set(PALETTE)
    assert all(np.array_equal(parts[1].position,(0,0,.25)) for parts in handles.values())
    first={k:tuple(v) for k,v in handles.items()}
    for parts in handles.values():
        for handle in parts:handle.visible=False
    update(SimpleNamespace(scene=Scene()),TF(),received,cfg,handles)
    assert len(calls)==3 and all(tuple(handles[k])==v for k,v in first.items())
    assert all(h.visible for parts in handles.values() for h in parts)
    assert all(np.array_equal(parts[1].position,(0,0,.25)) for parts in handles.values())
