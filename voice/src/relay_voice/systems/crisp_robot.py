"""Experimental wideband WOLA vocoder for the V8a character audition.

The harmonic clock is fixed, so a pitch tracker cannot introduce octave jumps.
Unvoiced speech and the upper consonant band retain their source spectrum.
This does not yet implement the V8b speaker-envelope normalisation.
"""
from pathlib import Path
import numpy as np
import yaml
from scipy.signal import butter, sosfilt


class CrispRobot:
    name = "v8"
    sample_rate = 24000
    hop = 120
    size = 480
    algorithmic_delay_ms = 15.0

    def __init__(self, config):
        self.config = yaml.safe_load(Path(config).read_text(encoding="utf-8"))
        c = self.config
        if c["sample_rate"] != self.sample_rate:
            raise ValueError("V8a requires 24 kHz internally")
        self.window = np.sqrt(np.hanning(self.size + 1)[:-1])
        self.history = np.zeros(self.size)
        self.pitch_history = np.zeros(960)
        self.ola = np.zeros(self.size)
        self.weights = np.zeros(self.size)
        self.clock = 0
        self.voicing = 0.0
        self.hp = butter(2, 65, btype="highpass", fs=self.sample_rate, output="sos")
        self.hp_state = np.zeros((len(self.hp), 2))
        bins = np.fft.rfftfreq(self.size, 1 / self.sample_rate)
        self.wet_band = np.clip((c["dry_above_hz"] - bins) / 1600, 0, 1)
        k = np.arange(-9, 10)
        self.kernel = np.exp(-0.5 * (k / 2.6) ** 2)
        self.kernel /= self.kernel.sum()
        # Precompute a continuous carrier period; block starts advance on its clock.
        self.period = self.sample_rate
        t = np.arange(self.period) / self.sample_rate
        self.carrier = np.zeros(self.period)
        for h in range(1, int(10800 / c["f0_hz"]) + 1):
            self.carrier += np.cos(2 * np.pi * h * c["f0_hz"] * t) / h ** 0.15
        self.carrier /= np.sqrt(np.mean(self.carrier ** 2))
        self.comb_samples = int(c["metal_delay_ms"] * self.sample_rate / 1000)
        self.comb = np.zeros(self.comb_samples)
        self.last = {}

    def reset(self):
        """Clear mutable stream state without rebuilding the fixed carrier."""
        for state in (self.history,self.pitch_history,self.ola,self.weights,self.hp_state,self.comb):
            state.fill(0)
        self.clock=0
        self.voicing=0.
        self.last={}

    def process_block(self, x):
        if x.shape != (self.hop,):
            raise ValueError("V8a expects 120 samples at 24 kHz")
        c = self.config
        x, self.hp_state = sosfilt(self.hp, x, zi=self.hp_state)
        self.history[:-self.hop] = self.history[self.hop:]
        self.history[-self.hop:] = x
        self.pitch_history[:-self.hop] = self.pitch_history[self.hop:]
        self.pitch_history[-self.hop:] = x
        p = self.pitch_history - self.pitch_history.mean()
        correlation = np.fft.irfft(np.abs(np.fft.rfft(p, n=2048)) ** 2)
        lags = np.arange(48, 343)
        # Correct the finite-history overlap rather than favouring short lags.
        energy = np.r_[0.0, np.cumsum(p * p)]
        denominator = np.sqrt((energy[-1] - energy[lags]) * energy[-1-lags])
        periodicity = float(np.max(correlation[lags] / np.maximum(denominator, 1e-12)))
        target = np.clip((periodicity - 0.28) / 0.30, 0, 1)
        if np.mean(p * p) < 1e-9:
            target = 0.0
        self.voicing += 0.5 * (target - self.voicing)
        spectrum = np.fft.rfft(self.history * self.window)
        carrier = self.carrier[(np.arange(self.size) + self.clock - self.size + self.hop) % self.period]
        carrier_spectrum = np.fft.rfft(carrier * self.window)
        envelope = np.sqrt(np.convolve(np.abs(spectrum) ** 2, self.kernel, mode="same"))
        carrier_envelope = np.sqrt(np.convolve(np.abs(carrier_spectrum) ** 2, self.kernel, mode="same"))
        robot = carrier_spectrum * envelope / np.maximum(carrier_envelope, 1e-8)
        mix = c["vocoder_mix"] * self.voicing * self.wet_band
        frame = np.fft.irfft(spectrum * (1 - mix) + robot * mix, n=self.size)
        self.ola += frame * self.window
        self.weights += self.window ** 2
        # The steady-state sqrt-Hann COLA sum is two. A fixed denominator also
        # avoids amplifying spectral leakage during the first partial windows.
        output = self.ola[:self.hop] / 2.0
        self.ola[:-self.hop] = self.ola[self.hop:]
        self.ola[-self.hop:] = 0
        self.weights[:-self.hop] = self.weights[self.hop:]
        self.weights[-self.hop:] = 0
        joined = np.r_[self.comb, output]
        metallic = output + c["metal_mix"] * joined[:self.hop]
        self.comb[:] = joined[-self.comb_samples:]
        # Fixed gain and continuous, memoryless safety saturation; no block AGC.
        output = 0.90 * np.tanh(c["output_gain"] * metallic / 0.90)
        self.clock = (self.clock + self.hop) % self.period
        self.last = {"periodicity": periodicity, "voicing": self.voicing,
                     "fixed_carrier_f0_hz": c["f0_hz"]}
        return output.astype(np.float32)
