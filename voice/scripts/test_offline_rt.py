"""Verify offline and callback processing agree, including deadline muting."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from eval.convert import convert
from relay_voice.rt.engine import Engine


def main():
    source = (.05*np.sin(2*np.pi*180*np.arange(4800)/48000)).astype(np.float32)
    rows = []
    for name in ["passthrough", "baseline", "lpc"]:
        expected, _, _ = convert(source, name)
        engine = Engine(name)
        status = SimpleNamespace(input_overflow=False, output_underflow=False)
        matched, overruns = 0, 0
        for i in range(0, len(source), 240):
            t = SimpleNamespace(inputBufferAdcTime=i/48000, outputBufferDacTime=i/48000+.03)
            out = np.empty((240, 2), dtype=np.float32)
            engine.callback(source[i:i+240, None], out, 240, t, status)
            event = engine.drain()[0]
            if event["overrun"]:
                assert not np.any(out)
                overruns += 1
            else:
                assert np.array_equal(out[:, 0], expected[i:i+240])
                assert np.array_equal(out[:, 0], out[:, 1])
                matched += 1
        rows.append({"system": name, "identical_nonoverrun_blocks": matched, "silent_overrun_blocks": overruns})
    Path("results/offline_rt_acceptance.json").write_text(json.dumps(rows, indent=2))
    print(rows)


if __name__ == "__main__":
    main()
