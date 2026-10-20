"""Human evidence must identify and preserve the selected recording build."""
import json
from pathlib import Path
import pytest
from p2.io import frozen_build as frozen


def test_freeze_accepts_evidence_and_rejects_changed_configuration(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);monkeypatch.setattr(frozen,'PATH',Path('freeze.json'))
    for folder in ['p2','configs','scripts','assets/robot']:Path(folder).mkdir(parents=True,exist_ok=True)
    for name in ['env.ps1','pyproject.toml','uv.lock','configs/cameras.yaml','p2/start.py']:
        Path(name).write_text('original')
    saved=frozen.fingerprint();frozen.PATH.write_text(json.dumps(saved))
    assert frozen.check()['build_hash']==saved['build_hash']
    Path('human_recording.txt').write_text('evidence is outside the build fingerprint')
    assert frozen.check()['build_hash']==saved['build_hash']
    Path('configs/cameras.yaml').write_text('changed')
    with pytest.raises(ValueError,match='configs/cameras.yaml'):frozen.check()


def test_runtime_scan_and_calibration_are_frozen(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);monkeypatch.setattr(frozen,'PATH',Path('freeze.json'))
    for name in frozen.INPUTS:
        path=Path(name);path.parent.mkdir(parents=True,exist_ok=True);path.write_text('original')
    saved=frozen.fingerprint();frozen.PATH.write_text(json.dumps(saved))
    assert frozen.check()['build_hash']==saved['build_hash']
    Path('assets/scan/old_map.ply').write_text('changed')
    with pytest.raises(ValueError,match='old_map.ply'):frozen.check()
