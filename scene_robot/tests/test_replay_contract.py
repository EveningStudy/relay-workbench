"""Timestamp and array fidelity at the replay/display audit boundary."""
import numpy as np
from p2.msgs import DisplayEvidence,CameraFrame,encode,decode
import pytest


def test_display_evidence_preserves_epoch_and_states():
    t=1792203541742322239
    packet=DisplayEvidence(t,12,np.array([[1.,2.,.9]],np.float32),np.array([0,1,2],np.int8),np.array([[0.,0.,.9]],np.float32),np.array([True]),np.array([t-100],np.int64))
    topic,copy=decode(encode('fusion/evidence',packet))
    assert topic=='fusion/evidence' and copy.t_ns==t
    assert copy.hit_ns[0]==t-100
    assert np.array_equal(copy.old_states,[0,1,2])
    assert copy.unknown.dtype==np.bool_


def test_private_unbiased_clock_cannot_enter_camera_transport():
    f=CameraFrame('head_left',1,100,200,'synthetic','pinhole',1,1,np.zeros((1,1,3),np.uint8),None,'none',{'true_capture_ns':100})
    with pytest.raises(ValueError,match='outside the operating contract'):encode('camera/head_left',f)


def test_delayed_observation_keeps_capture_epoch_and_follows_newer_state():
    from p2.io.episode import replay_schedule
    items=[(100,2,'frame',{'cam_id':'wrist_right','t_send_ns':400}),
           (200,0,'joints',{'t_ns':200}),
           (250,2,'frame',{'cam_id':'head_left','t_send_ns':270})]
    schedule=replay_schedule(items)
    assert [(delivery,kind,capture) for delivery,_,kind,_,capture in schedule]==[
        (200,'joints',200),(270,'frame',250),(400,'frame',100)]
    assert replay_schedule(items,'capture')[0][0]==100


def test_presentation_freezes_received_sequence_and_grows_age_until_recovery():
    from p2.eval.presentation_state import camera_observation
    billion=1_000_000_000
    samples=[{'t_dom_ns':billion,'latest_observations':{'wrist_right':
        {'seq':7,'t_capture_ns':700_000_000,'t_recv_ns':990_000_000}}},
        {'t_dom_ns':3*billion,'latest_observations':{'wrist_right':
        {'seq':8,'t_capture_ns':2_950_000_000,'t_recv_ns':2_990_000_000}}}]
    rows={('wrist_right',7):{'rgb':'last.jpg'},('wrist_right',8):{'rgb':'new.jpg'}}
    delayed=camera_observation(samples,rows,'wrist_right',billion)
    offline=camera_observation(samples,rows,'wrist_right',2*billion)
    recovered=camera_observation(samples,rows,'wrist_right',3*billion)
    assert delayed['state']=='LATE' and delayed['age_ms']==300
    assert offline['state']=='OFFLINE' and offline['seq']==7 and offline['age_ms']==1300
    assert recovered['state']=='OK' and recovered['seq']==8
