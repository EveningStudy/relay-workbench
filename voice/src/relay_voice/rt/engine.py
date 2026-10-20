"""No audio queue: one input block maps to one output block synchronously."""
import json
from pathlib import Path
import time
import numpy as np
from scipy.signal import firwin, lfilter
import sounddevice as sd
from relay_voice.systems import create_system


class Pipeline:
    """Stateful causal FIR resampling; exactly 240 -> 80 -> 240 samples.

    Both FIRs have group delay of 30 / 48000 seconds. No future samples
    are used. State is independent for each stream; zero padding only at EOF.
    """
    resampling_delay_ms = 1.25

    def __init__(self, system="passthrough", config=None):
        self.frames = 240
        self.config = config
        self.transparent = system == "passthrough"
        self.system = create_system(system, config)
        self.ratio = 2 if system == "v8" else 3
        self.taps = firwin(61, 7000, fs=48000)
        if system == "v8":
            self.taps = firwin(97, 10800, fs=48000)
            self.resampling_delay_ms = 2.0
        self.down_state = np.zeros(60)
        self.up_state = np.zeros(60)
        if system == "v8":
            self.down_state = np.zeros(len(self.taps)-1)
            self.up_state = np.zeros(len(self.taps)-1)

    @property
    def algorithmic_delay_ms(self):
        if self.transparent:
            return 0.0
        return self.resampling_delay_ms + self.system.algorithmic_delay_ms

    def process48(self, x):
        if len(x) != 240:
            raise ValueError("Pipeline requires a 240-sample block at 48 kHz")
        if self.transparent:
            # Identity is sample-rate independent. Preserve the native samples
            # for a genuine unprocessed anchor in both offline and live use.
            return self.system.process_block(x)
        down, self.down_state = lfilter(self.taps, [1.0], x, zi=self.down_state)
        converted = self.system.process_block(down[::self.ratio].astype(np.float32))
        if converted.shape != (240 // self.ratio,) or not np.isfinite(converted).all():
            raise ValueError("Invalid system output")
        up = np.zeros(240)
        up[::self.ratio] = converted
        result, self.up_state = lfilter(self.taps * self.ratio, [1.0], up, zi=self.up_state)
        return result.astype(np.float32)

    def reset(self):
        if hasattr(self.system,'reset'):
            self.system.reset()
        else:
            self.system=create_system(self.system.name, self.config)
        self.down_state.fill(0)
        self.up_state.fill(0)


def warm_system(system, config=None):
    """Exercise voiced branches before opening a device, using disposable state.

    Silence alone closes the gate and does not warm Numba's synthesis kernels.
    This generated signal is never played or used as an evaluation recording.
    """
    pipeline = Pipeline(system, config)
    count = 128 if system == "knn320" else 8
    for i in range(count):
        x = (.05*np.sin(2*np.pi*185*np.arange(i*240, (i+1)*240)/48000)).astype(np.float32)
        pipeline.process48(x)


FIELDS = ["sequence", "adc", "dac", "timestamp_delta_ms", "algorithmic_delay_ms",
          "processing_ms", "input_rms", "output_rms", "overrun", "input_overflow",
          "output_underflow", "safe_mode", "emergency", "variable_frames", "callback_ms"]


class Engine:
    def __init__(self, system="passthrough", config=None, capacity=4096, consistency=None):
        self.config = config
        self.consistency = consistency
        self.pipeline = consistency if system == 'consistency' else Pipeline(system, config)
        self.pending_system = None
        self.needs_reset = False
        self.ring = np.zeros((capacity, len(FIELDS)), dtype=np.float64)
        self.written, self.read, self.telemetry_lost = 0, 0, 0
        self.safe_mode, self.emergency = False, False
        self.error = None
        self.connection_state = 'idle'

    def switch(self, system):
        # Device block size changes only between stream lifetimes in run().
        self.pending_system = system

    def apply_switch(self):
        system = self.pending_system
        if system is not None:
            if system == 'consistency':
                if self.consistency is None:
                    raise RuntimeError('Consistency model was not loaded')
                self.consistency.reset()
                self.pipeline = self.consistency
            else:
                self.pipeline = Pipeline(system, self.config)
            self.pending_system = None
        self.safe_mode = False

    def reset_stream(self):
        if hasattr(self.pipeline, 'reset'):
            self.pipeline.reset()
        else:
            self.pipeline = Pipeline(self.pipeline.system.name, self.config)
        self.needs_reset = False

    def callback(self, indata, outdata, frames, times, status):
        start = time.perf_counter()
        outdata.fill(0)
        overrun = False
        variable = frames != self.pipeline.frames
        x = indata[:, 0]
        try:
            if self.emergency or variable or status.input_overflow or status.output_underflow:
                y = np.zeros(frames, dtype=np.float32)
                self.needs_reset = True
            elif self.safe_mode:
                y = np.zeros(frames, dtype=np.float32)
            else:
                if self.needs_reset:
                    self.reset_stream()
                y = self.pipeline.process48(x)
            processing_ms = (time.perf_counter() - start) * 1000
            if processing_ms > frames / 48:
                y.fill(0)
                overrun = True
                self.needs_reset = True
            outdata[:] = y[:, None]
        except Exception as exc:
            outdata.fill(0)
            self.safe_mode = True
            self.error = repr(exc)
            processing_ms = (time.perf_counter() - start) * 1000
        idx = self.written % len(self.ring)
        self.ring[idx] = [self.written, times.inputBufferAdcTime, times.outputBufferDacTime,
            (times.outputBufferDacTime - times.inputBufferAdcTime) * 1000,
            0.0 if self.safe_mode else self.pipeline.algorithmic_delay_ms, processing_ms,
            float(np.sqrt(np.mean(x * x))), float(np.sqrt(np.mean(outdata * outdata))),
            overrun, bool(status.input_overflow), bool(status.output_underflow),
            self.safe_mode, self.emergency, variable, 0.0]
        # Include output copy, levels and telemetry assignment in the deadline.
        # Only the final scalar updates below remain outside this observation.
        callback_ms = (time.perf_counter() - start) * 1000
        self.ring[idx, -1] = callback_ms
        if callback_ms > frames / 48:
            outdata.fill(0)
            self.ring[idx, FIELDS.index("overrun")] = 1
            self.ring[idx, FIELDS.index("output_rms")] = 0
            self.needs_reset = True
        self.written += 1

    def drain(self):
        end = self.written
        if end - self.read > len(self.ring):
            self.telemetry_lost += end - self.read - len(self.ring)
            self.read = end - len(self.ring)
        rows = self.ring[np.arange(self.read, end) % len(self.ring)].copy()
        self.read = end
        return [dict(zip(FIELDS, row.tolist())) for row in rows]


def open_stream(engine, input_device, output_device, exclusive=True):
    inp = sd.query_devices(input_device)
    out = sd.query_devices(output_device)
    if inp["hostapi"] != out["hostapi"]:
        raise ValueError("Input/output must use one host API")
    if "WASAPI" not in sd.query_hostapis(inp["hostapi"])["name"]:
        raise ValueError("Choose WASAPI device IDs; MME is not a supported default")
    return sd.Stream(device=(input_device, output_device), samplerate=48000, blocksize=engine.pipeline.frames,
        channels=(min(2, inp["max_input_channels"]), min(2, out["max_output_channels"])),
        dtype="float32", callback=engine.callback, latency="low",
        extra_settings=sd.WasapiSettings(exclusive=exclusive))


def connect_stream(engine, input_device, output_device, shared, event):
    """Try WASAPI exclusive, then shared; close failed partial opens."""
    modes = [False] if shared else [True, False]
    for exclusive in modes:
        candidate = None
        try:
            candidate = open_stream(engine, input_device, output_device, exclusive)
            candidate.start()
            event("stream_mode", exclusive=exclusive)
            return candidate
        except sd.PortAudioError as exc:
            if candidate is not None:
                candidate.close()
            if not exclusive:
                raise
            event("exclusive_failed_try_shared", error=repr(exc))


def run(engine, input_device, output_device, duration, path, shared=False, tick=None):
    """Reconnect in bounded exponential backoff. Telemetry never contains audio."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    start, disconnected, attempt, stream = time.monotonic(), None, 0, None
    with path.open("w", encoding="utf-8", buffering=1) as log:
        def event(kind, **kwargs):
            log.write(json.dumps({"event": kind, "elapsed_s": time.monotonic() - start, **kwargs}) + "\n")
        event("start", system=engine.pipeline.system.name, devices=[input_device, output_device],
              common_clock="Chris must verify a single physical headset/codec", exclusive=not shared)
        try:
            while time.monotonic() - start < duration and not engine.emergency:
                if engine.pending_system is not None:
                    if stream is not None:
                        stream.stop()
                        stream.close()
                        stream = None
                    engine.apply_switch()
                    event('mode_switch', system=engine.pipeline.system.name)
                if stream is None or not stream.active:
                    engine.connection_state = 'recovering'
                    if disconnected is None:
                        disconnected = time.monotonic()
                    if stream is not None:
                        stream.close()
                        stream = None
                    try:
                        engine.reset_stream()
                        stream = connect_stream(engine, input_device, output_device, shared, event)
                        event("stream_open", recovery_s=time.monotonic() - disconnected, latency=stream.latency)
                        engine.connection_state = 'running'
                        disconnected, attempt = None, 0
                    except sd.PortAudioError as exc:
                        delay = [0.5, 1.0, 2.0, 4.0][min(attempt, 3)]
                        event("open_failed", error=repr(exc), backoff_s=delay)
                        attempt += 1
                        if tick:
                            tick([], time.monotonic()-start)
                        time.sleep(delay)
                        continue
                rows = engine.drain()
                for row in rows:
                    log.write(json.dumps(row) + "\n")
                if engine.error:
                    event("callback_exception", error=engine.error)
                    engine.error = None
                if tick:
                    tick(rows, time.monotonic() - start)
                time.sleep(0.1)
        finally:
            engine.connection_state = 'stopped'
            if stream:
                stream.stop()
                stream.close()
            for row in engine.drain():
                log.write(json.dumps(row) + "\n")
            event("stop", telemetry_lost=engine.telemetry_lost, blocks=engine.written)
