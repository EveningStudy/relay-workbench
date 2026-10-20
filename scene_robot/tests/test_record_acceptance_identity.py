from pathlib import Path
from types import SimpleNamespace
import pytest
from p2.io import record_session, frozen_build


@pytest.mark.parametrize('synthetic',[False,True])
def test_synthetic_recording_cannot_be_mistaken_for_operator(tmp_path,monkeypatch,synthetic):
    monkeypatch.chdir(tmp_path);Path('data/logs').mkdir(parents=True)
    if synthetic:monkeypatch.setenv('P2_SYNTHETIC_ACCEPTANCE','1')
    else:monkeypatch.delenv('P2_SYNTHETIC_ACCEPTANCE',raising=False)
    checks=[];commands=[]
    monkeypatch.setattr(frozen_build,'check',lambda **kw:checks.append(kw))
    monkeypatch.setattr(record_session.subprocess,'Popen',lambda args,**kw:commands.append(args) or SimpleNamespace(poll=lambda:None,wait=lambda **kw:0))
    session=record_session.RecordSession();path=session.start('fixture')
    assert checks==[{'required':synthetic,'candidate':synthetic}]
    assert path==str(Path('data/m22/f_acceptance' if synthetic else 'human_inputs/07_teleop')/'fixture')
    args=commands[0]
    assert args[args.index('--origin')+1]==('scripted' if synthetic else 'teleop')
    assert args[args.index('--operator')+1]==('automated_acceptance' if synthetic else 'operator')
    session.close()
