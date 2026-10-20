"""Offline runner of the exact real-time Pipeline and process_block path."""
import hashlib
import time
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from relay_voice.rt.engine import Pipeline, warm_system


def read48(path):
    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if sr != 48000:
        from math import gcd
        factor = gcd(sr, 48000)
        audio = resample_poly(audio, 48000 // factor, sr // factor).astype(np.float32)
    return audio


def convert(audio48, system, config=None):
    pipeline = Pipeline(system, config)
    # A separate instance warms Numba without modifying the measured stream state.
    warm_system(system, config)
    length = len(audio48)
    padded = np.pad(audio48, (0, (-length) % 240))
    output = np.empty(len(padded), dtype=np.float32)
    times = []
    for start in range(0, len(padded), 240):
        t = time.perf_counter_ns()
        output[start:start+240] = pipeline.process48(padded[start:start+240])
        times.append((time.perf_counter_ns() - t) / 1e6)
    return output[:length], np.asarray(times), pipeline.algorithmic_delay_ms


def code_hash():
    digest = hashlib.sha256()
    for file in sorted(Path("src/relay_voice").rglob("*.py")):
        digest.update(file.read_bytes())
    return digest.hexdigest()
