import os
import time
import numpy as np
import pytest
from p2.io.live_capture import Session, frames, matching, capture_worker
from p2.io.live_test import measure_outage


DEVICE = {'backend': 'MSMF', 'index': 1, 'name': 'FHD Webcam', 'device_id': 'usb:fhd'}


def test_identity_survives_reorder_and_never_substitutes_other_camera():
    other = dict(DEVICE, index=1, name='DroidCam Video', device_id='virtual:droid')
    moved = dict(DEVICE, index=0)
    assert matching([other, moved], DEVICE) == moved
    assert matching([other], DEVICE) is None
    assert matching([dict(DEVICE,device_id='different:fhd')], DEVICE) is None
    fallback = dict(DEVICE, backend='DSHOW', device_id='dshow:fhd')
    assert matching([other, fallback], DEVICE) == fallback
    assert matching([fallback, dict(fallback, index=2)], DEVICE) is None


class FakeSession:
    def __init__(self, events):self.events=iter(events);self.closed=False
    def receive(self, timeout):
        event=next(self.events, ('error', 'device absent'))
        if isinstance(event, Exception):raise event
        return event
    def close(self):self.closed=True


@pytest.mark.parametrize('failure', [('error','unknown C++ exception'), EOFError(), TimeoutError()])
def test_die_return_fallback_backoff_and_full_reset(failure):
    sessions=[];backends=[];delays=[]
    def create(backend, selected):
        backends.append(backend)
        # First camera session dies, then absent across both backends, then returns.
        events=[('inventory',[]), failure]
        if len(sessions)==0:events=[('frame',10,None,DEVICE,100),failure]
        if len(sessions)==3:events=[('inventory',[dict(DEVICE,index=0)]),('frame',50,None,dict(DEVICE,index=0),103)]
        session=FakeSession(events);sessions.append(session);return session
    stream=frames(DEVICE,session_factory=create,sleep=delays.append,log=lambda _:None)
    assert next(stream)[0]==10
    assert next(stream)[0]==50
    stream.close()
    assert backends==['MSMF','MSMF','DSHOW','MSMF']
    assert delays==[.5,1.,2.]
    assert all(s.closed for s in sessions)


def test_without_reconnect_still_tries_dshow_fallback():
    backends=[]
    def create(backend, selected):
        backends.append(backend)
        return FakeSession([('error','MSMF unavailable')] if backend=='MSMF' else [('frame',1,None,DEVICE,2),('error','end')])
    assert len(list(frames(DEVICE,False,session_factory=create,sleep=lambda _:None,log=lambda _:None)))==1
    assert backends==['MSMF','DSHOW']


def test_backoff_is_capped_and_persists_until_camera_returns():
    attempts=[];delays=[]
    def create(backend, selected):
        attempts.append(backend)
        return FakeSession([('frame',1,None,DEVICE,1)] if len(attempts)==9 else [('error','absent')])
    stream=frames(DEVICE,session_factory=create,sleep=delays.append,log=lambda _:None)
    next(stream);stream.close()
    assert delays==[.5,1.,2.,4.,8.,8.,8.,8.]


def synthetic_worker(pipe, backend, selected, probe):
    """Fresh child simulates a native crash, a wedged read, or a live camera."""
    if selected=='crash':os._exit(7)
    if selected=='hang':time.sleep(30)
    if selected=='status':
        pipe.send(('inventory',[DEVICE]));pipe.send(('error','simulated native failure'));pipe.close();return
    pipe.send(('frame',time.time_ns(),np.zeros((2,3,3),dtype=np.uint8),DEVICE,os.getpid()))
    pipe.close()


def test_real_child_crash_watchdog_and_return():
    pids=[]
    for mode in ('crash','hang','return'):
        session=Session('MSMF',mode,worker=synthetic_worker);pids.append(session.process.pid)
        try:
            if mode=='crash':
                with pytest.raises(EOFError):session.receive(4)
            elif mode=='hang':
                with pytest.raises(TimeoutError):session.receive(.5)
            else:
                event=session.receive(4)
                assert event[0]=='frame' and event[2].shape==(2,3,3)
        finally:session.close()
        assert not session.process.is_alive()
    assert len(set(pids))==3


def test_schema_transport_preserves_inventory_and_failure():
    session=Session('MSMF','status',worker=synthetic_worker)
    try:
        assert session.receive(4)==('inventory',[DEVICE])
        assert session.receive(4)==('error','simulated native failure')
    finally:session.close()


def test_reconnect_generator_with_real_disposable_children():
    sessions=[]
    def create(backend, selected):
        session=Session(backend,'return',worker=synthetic_worker)
        sessions.append(session);return session
    stream=frames(DEVICE,session_factory=create,sleep=lambda _:None,log=lambda _:None)
    before=next(stream)
    # First child closes the pipe and dies after one frame. The supervisor must
    # detect EOF, dispose it, then receive from a newly spawned camera session.
    after=next(stream);stream.close()
    assert after[0]>before[0] and after[3]!=before[3]
    assert len(sessions)==2 and all(not s.process.is_alive() for s in sessions)


def test_worker_reenumerates_releases_and_uses_requested_backend(monkeypatch):
    inventories=[];opened=[];released=[];sent=[]
    monkeypatch.setattr('p2.io.live_capture.enumerate_devices',lambda backend: inventories.append(backend) or [dict(DEVICE,index=0)])
    class Capture:
        def __init__(self,index,backend):opened.append((index,backend))
        def isOpened(self):return True
        def read(self):return True,np.zeros((2,3,3),np.uint8)
        def release(self):released.append(True)
    class Pipe:
        def send(self,event):sent.append(event)
        def close(self):pass
    monkeypatch.setattr('p2.io.live_capture.cv2.VideoCapture',Capture)
    for backend in ('MSMF','DSHOW'):capture_worker(Pipe(),backend,DEVICE,True)
    assert inventories==['MSMF','DSHOW'] and len(released)==2
    assert [o[0] for o in opened]==[0,0] and opened[0][1]!=opened[1][1]
    assert [s[0] for s in sent]==['inventory','frame','inventory','frame']


def frame(t):return {'t_capture_ns':int(t*1e9),'t_recv_ns':int((t+.01)*1e9),'seq':int(t)}


def test_outage_includes_last_frame_before_prompt_and_first_after_return():
    result=measure_outage([frame(1),frame(2),frame(15),frame(16)],8e9,9e9)
    assert result['recovered'] and result['outage_gap_s']==13
    assert result['last_frame_before_outage']['seq']==2
    assert result['first_frame_after_outage']['seq']==15


@pytest.mark.parametrize('rows', [[frame(1),frame(2)], [frame(7),frame(15)], [frame(2),frame(8.5),frame(15)]])
def test_no_false_recovery_for_no_return_no_silence_or_premature_return(rows):
    result=measure_outage(rows,8e9,9e9)
    assert not result['recovered'] and result['outage_gap_s'] is None


def test_helper_channel_never_takes_a_project_port():
    """Regression: the helper bound 5602, so the UI's fusion publisher crashed (Chris's live test)."""
    import zmq
    from p2.io import live_capture
    class Idle:  # do not start a real camera child in this unit test
        def __init__(self, *a, **k): pass
        def start(self): pass
        def is_alive(self): return False
        def join(self, timeout=None): pass
    ctx = type('Ctx', (), {'Process': Idle})()
    original = live_capture.mp.get_context
    live_capture.mp.get_context = lambda kind: ctx
    blocker = zmq.Context.instance().socket(zmq.PUB)
    try:
        blocker.bind('tcp://127.0.0.1:5602')  # stand-in for the UI's fusion publisher
        session = Session('MSMF')
        port = int(session.endpoint.rsplit(':', 1)[1])
        assert not 5600 <= port <= 5619
        session.close()
    finally:
        blocker.close(); live_capture.mp.get_context = original


def test_live_test_fails_fast_when_a_child_dies(tmp_path):
    from p2.io.live_test import wait_for_children
    log = tmp_path / 'operator_ui.txt'; log.write_text('zmq.error.ZMQError: Address in use\n')
    class Dead:
        returncode = 1
        def poll(self): return 1
    with pytest.raises(RuntimeError, match='Address in use'):
        wait_for_children([Dead()], [log], timeout_s=1, probe=lambda: False, sleep=lambda s: None)


def test_live_test_waits_until_ui_serves(tmp_path):
    from p2.io.live_test import wait_for_children
    class Alive:
        returncode = None
        def poll(self): return None
    answers = iter([False, False, True])
    wait_for_children([Alive()], [tmp_path / 'ui.txt'], timeout_s=5, probe=lambda: next(answers), sleep=lambda s: None)
