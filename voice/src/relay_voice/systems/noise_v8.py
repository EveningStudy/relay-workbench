"""V9c signal-only wrapper; device pipeline and V8 character are unchanged."""
from pathlib import Path
import yaml
import numpy as np
from relay_voice.dsp.noise_control import NoiseControl
from .crisp_robot import CrispRobot

ROOT=Path(__file__).resolve().parents[3]


class NoiseControlledV8:
    name='v8'
    def __init__(self,config,noise_config=None):
        self.base=CrispRobot(config)
        c=noise_config or yaml.safe_load((ROOT/'configs/v9c_noise.yaml').read_text())
        c={**c,**c.get('v8',{})}
        extra=15 if c.get('spectral',False) else 0
        self.signal_delay_ms=self.base.algorithmic_delay_ms+extra
        self.algorithmic_delay_ms=self.signal_delay_ms+c['analysis_ms']+c['fade_ms']
        self.control=NoiseControl(24000,c,round(self.signal_delay_ms*24))
        self.last={}

    def reset(self):
        self.base.reset();self.control.reset();self.last={}

    def process_block(self,x):
        filtered,_=self.control.analyse(x)
        y=self.base.process_block(filtered)
        y*=self.control.output_mask(len(y))
        y=np.clip(y*self.control.config.get('post_gain',1.),-.9,.9).astype(np.float32)
        self.last={**self.base.last,'gate_open':self.control.open,'noise_floor_rms':self.control.floor}
        return y
