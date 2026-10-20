"""DSP acceptance on known synthetic signals; no human listening claims."""
import json
from pathlib import Path
import numpy as np
from scipy.signal import lfilter
from relay_voice.dsp.core import yin, levinson, autocorrelation, lpc_to_lsf, lsf_to_lpc, synthesize
from relay_voice.systems import create_system


def main():
    pitch = []
    for f in [70, 90, 150, 220, 350, 500]:
        x = np.sin(2*np.pi*f*np.arange(640)/16000)
        estimate, confidence = yin(x)
        error = abs(estimate/f-1)
        assert error < .02
        pitch.append({"true_hz": f, "estimated_hz": estimate, "relative_error": error, "confidence": confidence})
    rng = np.random.default_rng(42)
    target_a = np.convolve([1, -.8], [1, -1.4, .81])
    x = lfilter([1.], target_a, rng.standard_normal(32000)*.01)
    a, _ = levinson(autocorrelation(x, 18), 18)
    residual = lfilter(a, [1.], x)
    reconstructed = lfilter([1.], a, residual)
    reconstruction_error = float(np.sqrt(np.mean((x-reconstructed)**2)))
    assert reconstruction_error < 1e-8
    lsf = lpc_to_lsf(a)
    lsf_error = float(np.max(np.abs(lsf_to_lpc(lsf)-a)))
    assert lsf_error < 1e-6
    memory = np.zeros(18)
    chunks = [synthesize(residual[i:i+80], a, a, memory) for i in range(0, len(x), 80)]
    chunk_error = float(np.max(np.abs(np.concatenate(chunks)-reconstructed)))
    assert chunk_error < 1e-8
    robot = create_system("lpc")
    outputs = [robot.process_block(np.sin(2*np.pi*180*np.arange(i,i+80)/16000).astype(np.float32)*.05)
               for i in range(0, 16000, 80)]
    assert np.isfinite(outputs).all() and np.max(np.abs(outputs)) <= 1
    silence = [robot.process_block(np.zeros(80, dtype=np.float32)) for _ in range(200)]
    assert np.max(np.abs(silence[-1])) == 0
    result = {"evidence": "measured synthetic acceptance", "yin": pitch,
              "lpc_reconstruction_rms_error": reconstruction_error,
              "lsf_roundtrip_max_error": lsf_error, "fixed_filter_chunk_boundary_max_error": chunk_error,
              "silence_final_peak": float(np.max(np.abs(silence[-1]))),
              "human_quality": "pending; continuity test is not a listening judgment"}
    Path("results/dsp_acceptance.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
