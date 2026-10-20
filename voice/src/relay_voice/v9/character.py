"""Two deterministic low-depth robot colour stages for converted target speech.

No pitch shifting, stochastic excitation or ring modulation is introduced. Neural
conversion establishes identity; these feedforward resonances add static colour.
"""
import numpy as np
from scipy.signal import butter,sosfilt


class RobotStage:
    def __init__(self,variant=1,sample_rate=16000):
        if variant not in (1,2):raise ValueError("Robot stage variant must be 1 or 2")
        self.sample_rate=sample_rate
        self.variant=variant
        self.depth=.035 if variant==1 else .075
        self.delay=max(1,round(sample_rate*(.00125 if variant==1 else .002)))
        self.history=np.zeros(self.delay)
        self.hp=butter(1,55,btype="highpass",fs=sample_rate,output="sos")
        self.state=np.zeros((len(self.hp),2))
        self.algorithmic_delay_ms=0.0

    def process_block(self,x):
        x,self.state=sosfilt(self.hp,np.asarray(x,dtype=np.float32),zi=self.state)
        combined=np.r_[self.history,x]
        delayed=combined[:len(x)]
        self.history[:]=combined[-self.delay:]
        result=(x+self.depth*delayed)/(1+self.depth)
        return (.98*np.tanh(result/.98)).astype(np.float32)
