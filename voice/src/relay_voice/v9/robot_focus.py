"""Audible deterministic robot colour with dry upper consonants.

A fixed harmonic carrier removes pitch-tracker wobble. Only periodic low/mid
speech is resynthesised; unvoiced and upper-band detail retain the VC signal.
Human listening must decide clarity and character suitability.
"""
import numpy as np
from scipy.signal import butter, sosfilt


class FocusRobot:
    sample_rate = 16000
    hop = 80
    size = 320
    algorithmic_delay_ms = 15.0

    def __init__(self, strength):
        if strength not in (1, 2, 3):
            raise ValueError('Robot strength must be 1, 2 or 3')
        self.strength = strength
        self.wet = (.30, .55, .80)[strength - 1]
        self.metal = (.08, .14, .20)[strength - 1]
        self.history = np.zeros(self.size)
        self.pitch_history = np.zeros(640)
        self.ola = np.zeros(self.size)
        self.window = np.sqrt(np.hanning(self.size + 1)[:-1])
        self.clock = 0
        self.voicing = 0.
        self.hp = butter(1, 55, fs=self.sample_rate, btype='highpass', output='sos')
        self.hp_state = np.zeros((len(self.hp), 2))
        bins = np.fft.rfftfreq(self.size, 1 / self.sample_rate)
        self.band = np.clip((4700 - bins) / 1700, 0, 1)
        k = np.arange(-8, 9)
        self.kernel = np.exp(-.5 * (k / 2.2) ** 2)
        self.kernel /= self.kernel.sum()
        t = np.arange(self.sample_rate) / self.sample_rate
        self.carrier = sum(np.cos(2 * np.pi * h * 185 * t) / h ** .15 for h in range(1, 42))
        self.carrier /= np.sqrt(np.mean(self.carrier ** 2))
        self.delay = round(.00165 * self.sample_rate)
        self.comb = np.zeros(self.delay)

    def process_block(self, x):
        if x.shape != (self.hop,):
            raise ValueError('FocusRobot requires 80 samples at 16 kHz')
        x, self.hp_state = sosfilt(self.hp, x, zi=self.hp_state)
        self.history[:-self.hop] = self.history[self.hop:]
        self.history[-self.hop:] = x
        self.pitch_history[:-self.hop] = self.pitch_history[self.hop:]
        self.pitch_history[-self.hop:] = x
        p = self.pitch_history - self.pitch_history.mean()
        corr = np.fft.irfft(np.abs(np.fft.rfft(p, n=2048)) ** 2)
        lags = np.arange(32, 229)
        energy = np.r_[0., np.cumsum(p * p)]
        norm = np.sqrt(np.maximum(0, (energy[-1] - energy[lags]) * energy[-1 - lags]))
        periodicity = float(np.max(corr[lags] / np.maximum(norm, 1e-12)))
        target = float(np.clip((periodicity - .30) / .35, 0, 1)) if np.mean(p * p) > 1e-9 else 0.
        self.voicing += .3 * (target - self.voicing)
        spectrum = np.fft.rfft(self.history * self.window)
        indices = (np.arange(self.size) + self.clock - self.size + self.hop) % self.sample_rate
        carrier = np.fft.rfft(self.carrier[indices] * self.window)
        envelope = np.sqrt(np.convolve(np.abs(spectrum) ** 2, self.kernel, mode='same'))
        carrier_envelope = np.sqrt(np.convolve(np.abs(carrier) ** 2, self.kernel, mode='same'))
        synthetic = carrier * envelope / np.maximum(carrier_envelope, 1e-8)
        mix = self.wet * self.voicing * self.band
        frame = np.fft.irfft((1 - mix) * spectrum + mix * synthetic, n=self.size)
        self.ola += frame * self.window
        y = self.ola[:self.hop].copy() / 2
        self.ola[:-self.hop] = self.ola[self.hop:]
        self.ola[-self.hop:] = 0
        joined = np.r_[self.comb, y]
        coloured = (y + self.metal * joined[:self.hop]) / np.sqrt(1 + self.metal ** 2)
        self.comb[:] = joined[-self.delay:]
        self.clock = (self.clock + self.hop) % self.sample_rate
        return (.97 * np.tanh(coloured / .97)).astype(np.float32)


def render_robot(x, strength):
    stage = FocusRobot(strength)
    length = len(x)
    padded = np.pad(x, (0, (-length) % stage.hop + stage.size))
    y = np.concatenate([stage.process_block(padded[i:i + stage.hop]) for i in range(0, len(padded), stage.hop)])
    # Alignment is only for the audition file. The live path retains this delay.
    delay = round(stage.algorithmic_delay_ms * 16)
    return y[delay:delay + length]
