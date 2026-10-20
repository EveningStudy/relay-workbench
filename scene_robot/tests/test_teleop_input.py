import numpy as np
from p2.ui.teleop_input import PresetRamp, joint_limits


def test_presets_smooth_and_velocity_bounded():
    limits=joint_limits()
    for side in ('left','right'):
        for p in range(1,7):
            target={side+'_shoulder_pitch':-.2-.2*(p%3),side+'_elbow':-.4-.3*(p%3),
                    side+'_shoulder_roll':(-.4 if side=='left' else .4)*(p//3)}
            start={n:(-1. if 'pitch' in n else -.8 if 'elbow' in n else 0.) for n in target}
            ramp=PresetRamp(start,target,limits);prior=start
            assert 1<=ramp.duration<=2
            for _ in range(100):
                value=ramp.advance(.02)
                assert all(abs(value[n]-prior[n])/.02<=limits[n]['velocity']*.7+1e-8 for n in value)
                prior=value
            assert ramp.done
            assert all(np.isclose(value[n],target[n]) for n in target)


def test_stalls_and_joint_limits():
    limits=joint_limits();name='left_elbow'
    ramp=PresetRamp({name:0.},{name:-20.},limits)
    value=ramp.advance(5.)
    assert ramp.elapsed==.05 and abs(value[name])<.01
    assert ramp.target[name]==limits[name]['lower']
    assert ramp.duration>=1.5*2.4/(.7*limits[name]['velocity'])


def test_arm_routing_yaw_and_stop_cancel():
    import threading
    from types import SimpleNamespace
    from p2.ui.operator_ui import OperatorUI
    ui=object.__new__(OperatorUI);sent=[]
    ui.teleop_lock=threading.RLock();ui.preset=None;ui.side='left'
    ui.teleop_limits=joint_limits();ui.arm_banner=SimpleNamespace(content='')
    ui.joint_names=list(ui.teleop_limits);ui.q=np.zeros(len(ui.joint_names))
    ui.commands=SimpleNamespace(send=lambda topic,msg:sent.append(msg))
    ui.key('Q');assert sent[-1].values['velocity']==[0,0,1.0]
    ui.key('E');assert sent[-1].values['velocity']==[0,0,-1.0]
    for bracket,side in [(']','right'),('[','left')]:
        ui.key(bracket);assert side.upper()+' ARM SELECTED' in ui.arm_banner.content
        for key in '123456':
            ui.key(key);assert all(n.startswith(side+'_') for n in ui.preset.target)
    ui.send('stop',{});assert ui.preset is None
    count=len(sent);ui.tick_preset();assert len(sent)==count
