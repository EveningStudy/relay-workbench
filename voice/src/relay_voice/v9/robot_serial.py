"""Single-path full-band robot character for the revised strength-3 audition.

Signal flow: causal analytic FIR -> complex frequency translation -> real output
-> safety saturation. There is no dry/wet mix, delayed voice copy, independent
harmonic carrier or consonant bypass. Quadrature components describe one analytic
signal, not two separately audible voices. All frequencies use the same FIR grid.
"""
import numpy as np
from scipy.signal import lfilter


class SerialRobot:
    sample_rate = 16000
    hop = 80
    fir_samples = 257
    group_delay_samples = (fir_samples - 1) // 2
    algorithmic_delay_ms = group_delay_samples / 16
    shift_hz = 70
    cutoff_hz = 7400

    def __init__(self):
        k = np.arange(self.fir_samples) - self.group_delay_samples
        omega = 2 * np.pi * self.cutoff_hz / self.sample_rate
        real = np.zeros(self.fir_samples)
        imaginary = np.zeros(self.fir_samples)
        nonzero = k != 0
        real[nonzero] = np.sin(omega * k[nonzero]) / (np.pi * k[nonzero])
        imaginary[nonzero] = (1 - np.cos(omega * k[nonzero])) / (np.pi * k[nonzero])
        real[~nonzero] = 2 * self.cutoff_hz / self.sample_rate
        self.taps = (real + 1j * imaginary) * np.blackman(self.fir_samples)
        self.state = np.zeros(self.fir_samples - 1, np.complex128)
        # Integer-Hz shift repeats exactly on this fixed one-second oscillator.
        self.rotation = np.exp(2j * np.pi * self.shift_hz * np.arange(self.sample_rate) / self.sample_rate)
        self.position = 0

    def process_block(self, x):
        x = np.asarray(x, dtype=np.float32)
        if x.shape != (self.hop,):
            raise ValueError('SerialRobot requires 80 samples at 16 kHz')
        analytic, self.state = lfilter(self.taps, [1.], x, zi=self.state)
        rotation = self.rotation[(np.arange(self.hop) + self.position) % self.sample_rate]
        self.position = (self.position + self.hop) % self.sample_rate
        translated = np.real(analytic * rotation)
        return (.97 * np.tanh(translated / .97)).astype(np.float32)


def render_serial(x, compensate_delay=False):
    """Replay the production block path; optional file alignment is explicit."""
    stage = SerialRobot()
    drain = ((stage.fir_samples + stage.hop - 1) // stage.hop) * stage.hop
    padded = np.pad(np.asarray(x, np.float32), (0, (-len(x)) % stage.hop + drain))
    y = np.concatenate([stage.process_block(padded[i:i + stage.hop]) for i in range(0, len(padded), stage.hop)])
    start = stage.group_delay_samples if compensate_delay else 0
    return y[start:start + len(x)]
