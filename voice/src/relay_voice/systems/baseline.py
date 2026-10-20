import numpy as np


class Passthrough:
    name = "passthrough"
    algorithmic_delay_ms = 0.0

    def process_block(self, x16k):
        return np.asarray(x16k, dtype=np.float32).copy()


class Baseline:
    """Fixed pitch ratio, two causal delay taps and fixed ring modulation.

    Delay taps crossfade across a fixed window. There is no F0 estimation,
    speaker normalisation, or offline-only transformation.
    """
    name = "baseline"
    algorithmic_delay_ms = 40.0

    def __init__(self, ratio=1.18, ring_hz=30.0, depth=0.35):
        self.ratio, self.ring_hz, self.depth = ratio, ring_hz, depth
        self.buffer = np.zeros(2048, dtype=np.float64)
        self.pos = 0
        self.phase = 0.0
        self.samples = 0

    def process_block(self, x16k):
        y = np.empty(len(x16k), dtype=np.float32)
        span = 620.0
        for i, x in enumerate(x16k):
            self.buffer[self.pos] = x
            self.phase = (self.phase + (1.0 - self.ratio) / span) % 1.0
            value = 0.0
            for phase in (self.phase, (self.phase + 0.5) % 1.0):
                delay = 2.0 + phase * span
                tap = (self.pos - delay) % len(self.buffer)
                j = int(tap)
                value += (1.0 - abs(2.0 * phase - 1.0)) * (
                    self.buffer[j] * (1.0 - (tap - j)) + self.buffer[(j + 1) % len(self.buffer)] * (tap - j))
            modulation = 1.0 - self.depth + self.depth * np.cos(2 * np.pi * self.ring_hz * self.samples / 16000)
            y[i] = np.clip(value * modulation, -0.98, 0.98)
            self.samples += 1
            self.pos = (self.pos + 1) % len(self.buffer)
        return y
