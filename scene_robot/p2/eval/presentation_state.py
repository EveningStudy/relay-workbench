"""Presentation selects only observations actually received by the operating UI."""
from bisect import bisect_right
from p2.ui.camera_status import state


def sample_at(samples,host_ns):
    index=bisect_right([s['t_dom_ns'] for s in samples],host_ns)-1
    return samples[index] if index>=0 else None


def camera_observation(samples,rows_by_seq,cam,host_ns):
    sample=sample_at(samples,host_ns)
    latest=sample.get('latest_observations',{}).get(cam) if sample else None
    if latest is None:return {'state':'WAITING','seq':None,'age_ms':None,'row':None}
    age=(host_ns-latest['t_capture_ns'])/1e6
    silence=(host_ns-latest['t_recv_ns'])/1e6
    return {'state':state(host_ns,latest['t_recv_ns'],age,0),
        'seq':latest['seq'],'age_ms':age,'silence_ms':silence,
        'row':rows_by_seq.get((cam,latest['seq'])),
        't_capture_ns':latest['t_capture_ns'],'t_recv_ns':latest['t_recv_ns'],
        'sample_t_dom_ns':sample['t_dom_ns']}
