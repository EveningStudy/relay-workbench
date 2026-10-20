"""Audited MeanVC2 loader and bounded synchronous streaming adapter.

One input packet enters inference in the callback. The fixed output reservoir
only reconciles the upstream 120/240 ms vocoder cadence with 160 ms device I/O;
it cannot grow, and is discarded on starvation, overflow, deadline or reconnect.
"""
from pathlib import Path
import sys
import numpy as np
from scipy.signal import firwin, lfilter
from relay_voice.v9.robot_serial import SerialRobot

ROOT = Path(__file__).resolve().parents[3]


def load_runner(embedding=None):
    import torch
    sys.path.insert(0, str(ROOT / 'third_party/meanvc2/upstream/runtime'))
    import run_rt
    original_load = torch.nn.Module.load_state_dict
    original_init, original_extract = run_rt.init_speaker_model, run_rt.extract_embedding
    def checked(module, state, *args, **kwargs):
        result = original_load(module, state, *args, **kwargs)
        permitted = {'cache_embed.weight', 'cache_embed.bias'} if type(module).__name__ == 'DiT' else set()
        if set(result.missing_keys) - permitted:
            raise RuntimeError('Missing active model weights: ' + str(result))
        return result
    torch.nn.Module.load_state_dict = checked
    if embedding is not None:
        target = torch.from_numpy(np.load(embedding)).float()
        run_rt.init_speaker_model = lambda *a, **k: None
        run_rt.extract_embedding = lambda *a, **k: target
    try:
        runner = run_rt.VCRunner(str(ROOT / 'references/raw_02.wav'), device='cpu', model='120ms')
    finally:
        torch.nn.Module.load_state_dict = original_load
        run_rt.init_speaker_model, run_rt.extract_embedding = original_init, original_extract
    def reject(*args):
        raise RuntimeError('Unused untrained cache branch executed')
    runner.vc.cache_embed.register_forward_pre_hook(reject)
    torch.set_num_threads(4)
    return runner


class ConsistencyPipeline:
    frames = 7680
    # No physical E2E claim: variable model startup is additional to these FIRs.
    algorithmic_delay_ms = 9.25
    name = 'consistency'
    capacity = 6400
    ingress = 2560

    def __init__(self, runner, shift_hz=70, noise_config=None):
        self.runner = runner
        self.shift_hz = shift_hz
        self.system = self
        self.taps = firwin(61, 7000, fs=48000)
        import yaml
        self.noise_config = noise_config or yaml.safe_load((ROOT/'configs/v9c_noise.yaml').read_text())
        self.noise_config={**self.noise_config,**self.noise_config.get('consistency',{})}
        self.noise_enabled=self.noise_config.get('enabled',True)
        self.reset()

    def reset(self):
        import torch
        self.runner._init_cache()
        torch.manual_seed(42)
        self.robot = SerialRobot()
        self.robot.shift_hz = self.shift_hz
        self.robot.rotation = np.exp(2j*np.pi*self.shift_hz*np.arange(16000)/16000)
        self.down = np.zeros(60)
        self.up = np.zeros(60)
        self.slot = np.zeros(self.capacity, np.float32)
        self.count = 0
        self.started = False
        self.silent = 0
        self.gain = 0.
        self.max_count = 0
        self.dropped = 0
        from relay_voice.dsp.noise_control import NoiseControl
        extra=240 if self.noise_config.get('spectral',False) else 0
        input_allowance=self.noise_config.get('input_filter_budget_ms',0)
        self.control=NoiseControl(16000,self.noise_config,128+extra+round(input_allowance*16)) if self.noise_enabled else None
        analysis=max(self.noise_config['analysis_ms'],32 if self.noise_config.get('learned_vad',False) else 0)
        self.algorithmic_delay_ms=(9.25+extra/16+analysis+self.noise_config['fade_ms']+input_allowance) if self.noise_enabled else 9.25

    def invalidate(self):
        self.reset()

    def process_block(self, x):
        if x.shape != (self.ingress,):
            raise ValueError('MeanVC2 ingress must be 2560 samples at 16 kHz')
        rms=float(np.sqrt(np.mean(x*x)))
        if self.control is not None:x,mask=self.control.analyse(x)
        # Preserve V9b model-state decisions; the adaptive VAD controls output,
        # not the VC cache. A microphone noise floor is not model reset input.
        self.silent=self.silent+1 if rms<.0003 else 0
        if self.silent>=4:
            if self.silent==4:
                self.runner._init_cache();self.count=0;self.started=False
                self.robot=SerialRobot();self.robot.shift_hz=self.shift_hz
                self.robot.rotation=np.exp(2j*np.pi*self.shift_hz*np.arange(16000)/16000)
            if self.control is not None:self.control.rebase()
            self.gain=0.
            return np.zeros(self.ingress,np.float32)
        y = self.runner.process_chunk(x)
        y = np.empty(0, np.float32) if y is None else np.asarray(y, np.float32)
        if len(y) > 3840 or len(y) % 80 or not np.isfinite(y).all():
            raise ValueError('Invalid upstream output packet')
        if len(y):
            y = np.concatenate([self.robot.process_block(y[i:i+80]) for i in range(0,len(y),80)])
            # Decisions advance by generated content samples, then travel with
            # that content through the existing cadence reservoir. Startup and
            # variable vocoder batches therefore do not desynchronise the gate.
            if self.control is not None:
                y *= self.control.output_mask(len(y))
                y *= self.noise_config.get('post_gain',1.)
        if self.count + len(y) > self.capacity:
            self.dropped += self.count
            self.count = 0
            self.started = False
        self.slot[self.count:self.count+len(y)] = y
        self.count += len(y)
        self.max_count = max(self.max_count, self.count)
        # Startup reserve accommodates the 120/240 ms cadence without recurring
        # partial blocks. Fixed-capacity state, no worker or catch-up queue.
        if not self.started and self.count >= self.ingress:
            self.started = True
        out = np.zeros(self.ingress, np.float32)
        if self.started:
            if self.count < self.ingress:
                self.dropped += self.count
                self.count = 0
                self.started = False
                self.gain = 0.
            else:
                out[:] = self.slot[:self.ingress]
                self.count -= self.ingress
                self.slot[:self.count] = self.slot[self.ingress:self.ingress+self.count]
                ramp = np.minimum(1., self.gain + np.arange(1,self.ingress+1)/320)
                out *= ramp
                self.gain = float(ramp[-1])
        return out

    def process48(self, x):
        if x.shape != (self.frames,):
            raise ValueError('Consistency mode uses a 160 ms native callback')
        down, self.down = lfilter(self.taps, [1.], x, zi=self.down)
        y = self.process_block(down[::3].astype(np.float32))
        up = np.zeros(self.frames)
        up[::3] = y
        result, self.up = lfilter(self.taps*3, [1.], up, zi=self.up)
        return np.clip(result, -.98, .98).astype(np.float32)
