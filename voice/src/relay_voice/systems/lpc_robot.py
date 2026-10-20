"""Causal LPC speaker-normalising robot vocoder. No audio lookahead or queue."""
from pathlib import Path
import numpy as np
from scipy.signal import butter, sosfilt, lfilter
import yaml
from relay_voice.dsp.core import yin, levinson, autocorrelation, lpc_to_lsf, lsf_to_lpc, synthesize, character_fx


class LPCRobot:
    name = "lpc"
    # Past-only analysis windows are not buffering delays. FIR delay is in Pipeline.
    algorithmic_delay_ms = 0.0

    def __init__(self, config=None):
        file = Path(config) if config else Path(__file__).resolve().parents[3]/"configs/relay_voice_v1.yaml"
        self.config = yaml.safe_load(file.read_text())
        c = self.config
        self.order = int(c["lpc_order"])
        assert self.order % 2 == 0
        self.hp = butter(2, 70, btype="highpass", fs=16000, output="sos")
        self.hp_state = np.zeros((len(self.hp), 2))
        self.history = np.zeros(640)
        self.pre_history = np.zeros(400)
        self.pre_state = np.zeros(1)
        self.de_state = np.zeros(1)
        self.memory = np.zeros(self.order)
        self.a = np.r_[1., np.zeros(self.order)]
        self.lsf = np.linspace(0, np.pi, self.order+2)[1:-1]
        self.gain = 1.
        self.phase = 0.
        self.log_mean, self.log_var = np.log(c["relay_f0_hz"]), .08
        self.centroid = float(c["envelope_target_hz"])
        self.f0 = c["relay_f0_hz"]
        self.noise = np.full(201, 1e-6)
        self.noise_floor = 1e-5
        self.silent_blocks, self.adapt_blocks, self.gate = 0, 200, False
        self.comb = np.zeros(max(1, int(c["comb_delay_ms"]*16)))
        self.comb_pos, self.samples = 0, 0
        self.rng = np.random.default_rng(20261016)
        self.last = {}

    def process_block(self, x16k):
        if len(x16k) != 80:
            raise ValueError("LPC expects exactly 80 samples at 16 kHz")
        c = self.config
        x, self.hp_state = sosfilt(self.hp, x16k, zi=self.hp_state)
        rms = float(np.sqrt(np.mean(x*x)+1e-16))
        self.noise_floor = min(rms, self.noise_floor*1.0002+1e-9)
        threshold = max(10**(c["gate_dbfs"]/20), self.noise_floor*1.5)
        self.gate = rms > threshold*(0.8 if self.gate else 1.2)
        if not self.gate:
            self.silent_blocks += 1
            self.history[:-80], self.history[-80:] = self.history[80:], 0.
            if self.silent_blocks >= 80:
                self.adapt_blocks = 100
                self.memory.fill(0)
                self.pre_history.fill(0)
                self.de_state.fill(0)
                self.comb.fill(0)
            self.last = {"gate": False, "source_f0": 0., "output_f0": 0., "confidence": 0.}
            return np.zeros(80, dtype=np.float32)
        self.silent_blocks = 0
        desired = min(10**(c["agc_max_db"]/20), 10**(c["agc_target_dbfs"]/20)/max(rms, 1e-6))
        self.gain += (0.25 if desired < self.gain else 0.005)*(desired-self.gain)
        conditioned = x*self.gain
        self.history[:-80], self.history[-80:] = self.history[80:], conditioned
        source_f0, confidence = yin(self.history)
        voiced = confidence > c["voiced_threshold"] and rms > threshold*2
        alpha = 1-np.exp(-.005/(.15 if self.adapt_blocks else c["adaptation_seconds"]))
        if voiced:
            logf = np.log(source_f0)
            # Sudden sustained shifts accelerate adaptation without looking ahead.
            if abs(logf-self.log_mean) > .55:
                self.adapt_blocks = max(self.adapt_blocks, 60)
            error = logf-self.log_mean
            self.log_mean += alpha*error
            self.log_var = (1-alpha)*self.log_var+alpha*error*error
            relative = np.clip(error/max(np.sqrt(self.log_var), .08), -2, 2)/2*c["intonation_semitones"]
            relative = (1-c["pitch_quantization"])*relative+c["pitch_quantization"]*np.round(relative)
            target = c["relay_f0_hz"]*2**(relative/12)
            self.f0 += .25*(target-self.f0)
        if self.adapt_blocks:
            self.adapt_blocks -= 1
        pre, self.pre_state = lfilter([1., -.97], [1.], conditioned, zi=self.pre_state)
        self.pre_history[:-80], self.pre_history[-80:] = self.pre_history[80:], pre
        spectrum = np.fft.rfft(self.pre_history)
        magnitude = np.abs(spectrum)
        self.noise = np.minimum(magnitude, self.noise*1.0005+1e-6)
        denoised = np.fft.irfft(spectrum*np.maximum(.25, 1-c["spectral_subtraction"]*self.noise/np.maximum(magnitude, 1e-8)), n=400)
        frame = denoised*np.hamming(400)
        a, residual = levinson(autocorrelation(frame, self.order), self.order)
        power = 1/np.maximum(np.abs(np.fft.rfft(a, n=1024))**2, 1e-8)
        frequencies = np.fft.rfftfreq(1024, 1/16000)
        band = (frequencies > 300) & (frequencies < 3500)
        observed = float(frequencies[band]@power[band]/max(power[band].sum(), 1e-8))
        if voiced:
            self.centroid += alpha*(observed-self.centroid)
        warp = np.clip(self.centroid/c["envelope_target_hz"], .82, 1.22)**c["envelope_strength"]
        warped = np.interp(frequencies*warp, frequencies, power, right=power[-1])
        r = np.fft.irfft(warped, n=1024)[:self.order+1]
        target_a, _ = levinson(r, self.order)
        target_a *= .996**np.arange(self.order+1)
        try:
            target_lsf = lpc_to_lsf(target_a)
        except ValueError:
            target_lsf = self.lsf.copy()
        smooth_lsf = self.lsf*.55+target_lsf*.45
        midpoint_a = lsf_to_lpc((self.lsf+smooth_lsf)/2)
        next_a = lsf_to_lpc(smooth_lsf)
        indices = np.arange(80)
        phases = (self.phase+indices*self.f0/16000)%1
        self.phase = (self.phase+80*self.f0/16000)%1
        # Band-limited harmonic excitation with deterministic character shape.
        excitation = np.zeros(80)
        for harmonic in range(1, min(35, int(7000/self.f0))+1):
            excitation += np.cos(2*np.pi*harmonic*phases)/harmonic**.65
        excitation /= max(float(np.sqrt(np.mean(excitation**2))), 1e-8)
        noise = self.rng.standard_normal(80)
        blend = np.clip((confidence-c["voiced_threshold"])/max(1-c["voiced_threshold"], .01), 0, 1) if voiced else 0.
        excitation = excitation*blend + noise*np.sqrt(max(0, 1-blend*blend))
        excitation *= np.sqrt(max(residual/np.sum(np.hamming(400)**2), 1e-12))
        first = synthesize(excitation[:40], self.a, midpoint_a, self.memory)
        second = synthesize(excitation[40:], midpoint_a, next_a, self.memory)
        synthesized = np.r_[first, second]
        self.a, self.lsf = next_a, smooth_lsf
        synthesized, self.de_state = lfilter([1.], [1., -.97], synthesized, zi=self.de_state)
        # Conservative variants preserve part of the conditioned residual waveform.
        result = c["robot_mix"]*synthesized+(1-c["robot_mix"])*conditioned
        result, self.comb_pos = character_fx(result, self.comb, self.comb_pos, c["comb_feedback"],
            c["ring_depth"], c["ring_hz"], self.samples, c["output_gain"])
        self.samples += 80
        self.last = {"gate": True, "source_f0": source_f0, "output_f0": self.f0,
                     "confidence": confidence, "warp": warp}
        return result
