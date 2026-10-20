"""Final human choices change presentation, not fusion or evaluation thresholds."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
import yaml
from p2.ui.presentation_ui import OperatorUI
from p2.ui.live_points import Samples
from p2.scene.chair import chair_boxes
from p2.eval.m22_latency_gate import assess


def test_final_defaults_and_chair():
    style=yaml.safe_load(Path('configs/ui.yaml').read_text())
    scene=yaml.safe_load(Path('configs/scene.yaml').read_text())
    assert style['crisp_live']['enabled'] is False
    assert style['display_backend']=='m20_points'
    assert style['show_floor'] and style['show_stale']
    assert not style['change_markers'] and not style['show_camera_frustums'] and not style['enlarged_labels']
    assert 'chair' not in scene and len(chair_boxes(scene))==2


def test_optional_depth_toggle_releases_history_and_hides_other_mode():
    ui=OperatorUI.__new__(OperatorUI)
    ui.style=yaml.safe_load(Path('configs/m22/presentation_ui.yaml').read_text())
    ui.fusion=SimpleNamespace(cfg=yaml.safe_load(Path('configs/fusion.yaml').read_text()),observation_sink=None)
    ui.depth_toggle=SimpleNamespace(value=True);ui.recent=None
    ui.cloud_handles={n:SimpleNamespace(visible=True) for n in ('/live','/floor_live','/live_depth')}
    ui.sync_live_mode()
    assert ui.recent and ui.fusion.observation_sink==ui.recent.accept
    assert all(not h.visible for h in ui.cloud_handles.values())
    ui.live_telemetry={'points':10};ui.depth_toggle.value=False;ui.sync_live_mode()
    assert ui.recent is None and ui.fusion.observation_sink is None
    assert not ui.live_telemetry and len(ui.live_samples.points)==0
    ui.sync_live_mode()  # repeated off state must not allocate a hidden sampler
    assert ui.recent is None


def test_disabled_aids_do_not_submit_or_create_hidden_nodes():
    from p2.ui.display_updates import MarkerNodes
    ui=OperatorUI.__new__(OperatorUI)
    ui.style=yaml.safe_load(Path('configs/m22/presentation_ui.yaml').read_text());ui.last_aids=0
    ui.change_toggle=SimpleNamespace(value=False);ui.camera_toggle=SimpleNamespace(value=False)
    ui.label_toggle=SimpleNamespace(value=False);ui.camera_handles={};ui.marker_nodes=MarkerNodes()
    submitted=[]
    ui.marker_worker=SimpleNamespace(submit=lambda *a:submitted.append(a),poll=lambda:None)
    ui.update_aids(1_000_000_000,None,None,None)
    assert not submitted and not ui.marker_nodes.nodes
    ui.change_toggle.value=True;ui.change_rows=[]
    ui.mask=SimpleNamespace(states=[],cluster_trace=[]);ui.live_samples=Samples.empty()
    ui.server=SimpleNamespace(scene=None)
    ui.update_aids(2_000_000_000,None,None,None)
    assert len(submitted)==1


@pytest.mark.parametrize('p95,mode,nonempty,passes',[(149.9,'voxel',True,True),(150,'voxel',True,False),
    (149,'crisp',True,False),(149,'voxel',False,False)])
def test_final_latency_gate_retains_strict_target(tmp_path,monkeypatch,p95,mode,nonempty,passes):
    monkeypatch.chdir(tmp_path)
    baseline=Path('data/perf/m17_final/nominal');baseline.mkdir(parents=True)
    (baseline/'raw.json').write_text(json.dumps({'stages_ms':{'capture_dom':{'p95':140.91}}}))
    out=Path('run');out.mkdir()
    (out/'raw.json').write_text(json.dumps({'stages_ms':{'capture_dom':{'p95':p95,'n':100}},
        'load':{'gpu_util_before':0,'contended':False},'crisp_live':{'points':{'max':0}}}))
    (out/'ui.yaml').write_text('crisp_live:\n  enabled: false\n')
    (out/'browser.json').write_text(json.dumps({'page_errors':[],'console_errors':[],
        'samples':[{'live_display_mode':mode,'live_voxel_points':10 if nonempty else 0}]}))
    (out/'contention.json').write_text('{"contended":false}')
    assert assess(out,'voxel')['pass'] is passes
