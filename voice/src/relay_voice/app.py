"""Native Windows wired-headphone entry point."""
import argparse
from collections import deque
import msvcrt
from pathlib import Path
import numpy as np
import psutil
from rich.live import Live
from rich.table import Table
from relay_voice.rt.engine import Engine, run, warm_system


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=int, required=True)
    p.add_argument("--output", type=int, required=True)
    p.add_argument("--same-clock", action="store_true", help="Confirm both endpoints are on the same codec")
    p.add_argument("--system", default="v8", choices=["passthrough", "baseline", "lpc", "v8", "consistency"])
    p.add_argument('--low-only', action='store_true', help='Skip neural model loading; key 4 is disabled')
    p.add_argument("--seconds", type=float, default=600)
    p.add_argument("--shared", action="store_true")
    p.add_argument("--config", type=Path)
    p.add_argument("--log", default="results/live.jsonl")
    args = p.parse_args()
    if args.config is None:
        args.config = Path('configs/v8a_B.yaml')
    if args.low_only and args.system == 'consistency':
        p.error('--low-only cannot start consistency mode')
    if not args.same_clock:
        p.error("Confirm a single physical audio clock using --same-clock. Separate USB/Realtek clocks are unsupported.")
    character = "v8"
    for system in ("passthrough", "baseline", character):
        warm_system(system, args.config)
    consistency = None
    if not args.low_only:
        import yaml
        from relay_voice.v9.meanvc_live import ConsistencyPipeline, load_runner
        c = yaml.safe_load(Path('configs/v9b_final.yaml').read_text())
        runner = load_runner(c['target_embedding'])
        consistency = ConsistencyPipeline(runner, c['shift_hz'])
        consistency.process48(np.zeros(consistency.frames, np.float32))
        consistency.reset()
    engine = Engine(args.system, args.config, consistency=consistency)
    history = deque(maxlen=2000)
    process = psutil.Process()
    process.cpu_percent()
    with Live(refresh_per_second=5) as live:
        def tick(rows, elapsed):
            history.extend(rows)
            if msvcrt.kbhit():
                key = msvcrt.getwch()
                if key in ("q", " ", "\x1b"):
                    engine.emergency = True
                elif key in "123":
                    engine.switch({"1": "passthrough", "2": "baseline", "3": character}[key])
                elif key == '4' and consistency is not None:
                    engine.switch('consistency')
            table = Table(title="Relay | 1 bypass 2 baseline 3 low latency 4 consistency | Space stop")
            table.add_column("Metric")
            table.add_column("Value")
            table.add_row("System", engine.pipeline.system.name)
            table.add_row("State", "SAFE MUTE" if engine.safe_mode else engine.connection_state.upper())
            if history:
                last = history[-1]
                latency = [r["timestamp_delta_ms"] + r["algorithmic_delay_ms"] for r in history]
                table.add_row("Driver timestamp + declared DSP p50 / p95 (ms)", str(np.percentile(latency, [50, 95])))
                if engine.pipeline.system.name=='consistency':
                    table.add_row('Neural startup/cadence delay', 'ADDITIONAL; excluded from the partial display above')
                table.add_row("Input / output RMS", f'{last["input_rms"]:.4f} / {last["output_rms"]:.4f}')
                table.add_row("Activity", "Speech / noise" if last["input_rms"] > 0.005 else "Silence")
            table.add_row("CPU process %", str(process.cpu_percent()))
            table.add_row("Elapsed seconds", f"{elapsed:.1f}")
            table.add_row("Physical mouth-to-ear latency", "PENDING PHONE VALIDATION")
            live.update(table)
        run(engine, args.input, args.output, args.seconds, args.log, args.shared, tick)


if __name__ == "__main__":
    main()
