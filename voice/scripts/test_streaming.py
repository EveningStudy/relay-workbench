"""Software acceptance with synthetic blocks; no hardware claims."""
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from relay_voice.rt.engine import Engine, Pipeline


def main():
    results = {}
    times = SimpleNamespace(inputBufferAdcTime=1., outputBufferDacTime=1.03)
    status = SimpleNamespace(input_overflow=False, output_underflow=False)
    x = np.sin(np.arange(240, dtype=np.float32) * 0.1)[:, None] * 0.1
    for name in ["passthrough", "baseline"]:
        engine = Engine(name, capacity=4)
        for _ in range(12):
            out = np.empty((240, 2), dtype=np.float32)
            engine.callback(x, out, 240, times, status)
            assert np.isfinite(out).all()
            assert np.max(np.abs(out)) <= 1
        rows = engine.drain()
        assert len(rows) == 4 and engine.telemetry_lost == 8
        results[name] = {"blocks": engine.written, "telemetry_lost": engine.telemetry_lost}
    engine = Engine()
    class Broken:
        # Delivered engine contract includes a fixed callback block size.
        frames = 240
        def process48(self, x):
            raise RuntimeError("injected failure")
    engine.pipeline = Broken()
    out = np.ones((240, 1), dtype=np.float32)
    engine.callback(x, out, 240, times, status)
    assert engine.safe_mode and not np.any(out)
    engine.callback(x, out, 240, times, status)
    assert engine.safe_mode and not np.any(out)
    results["exception"] = "first and subsequent faulted blocks remain safely muted"
    pipeline = Pipeline()
    impulse = np.zeros(240, dtype=np.float32)
    impulse[0] = 1
    impulse_output = pipeline.process48(impulse)
    results["transparent_impulse_peak_samples_48k"] = int(np.argmax(np.abs(impulse_output)))
    assert np.array_equal(impulse_output, impulse)
    pipeline = Pipeline("baseline")
    from relay_voice.systems.baseline import Passthrough
    pipeline.system = Passthrough()
    filtered = pipeline.process48(impulse)
    results["fir_impulse_peak_samples_48k"] = int(np.argmax(np.abs(filtered)))
    assert results["fir_impulse_peak_samples_48k"] == 60
    Path("results/v1_acceptance.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
