"""Original synthetic DSP/callback/metric/parity suites, plus current default."""
import importlib.util
from pathlib import Path
import pytest

@pytest.mark.parametrize('name',['test_dsp','test_streaming','test_metrics','test_offline_rt'])
def test_original_suite(name):
    path=Path('scripts')/(name+'.py')
    spec=importlib.util.spec_from_file_location('legacy_'+name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()

def test_default_replay():
    import numpy as np
    from relay_voice.rt.engine import Pipeline
    t=np.arange(48000)/48000
    x=(.08*np.sin(2*np.pi*180*t)+.02*np.sin(2*np.pi*360*t)).astype(np.float32)
    p=Pipeline('v8',Path('configs/v8a_B.yaml'))
    y=np.concatenate([p.process48(x[i:i+240]) for i in range(0,len(x),240)])
    assert y.shape==x.shape and np.isfinite(y).all()
    assert .001 < np.max(np.abs(y)) <= 1
