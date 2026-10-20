"""Render selected historical numbers, not a benchmark rerun."""
from pathlib import Path
import argparse,csv,json
ROOT=Path(__file__).resolve().parents[1]

def render():
    lines=['# Results','',
        'Historical measurements below belong to the original build. This renamed copy',
        'does not inherit its freeze hashes. Retained CSV/JSON summaries are under',
        '`results/`; full raw recordings, models and long telemetry are not bundled.',
        'Run `python scripts/results.py --check` to verify this page against the retained',
        'tables. That checks transcription and arithmetic, not new inference or hardware.','',
        '## Voice quality','',
        'Twelve heldout speakers, five clips each, mostly read English. EER measures',
        'source-identity discrimination. DNSMOS and embedding similarity are imperfect',
        'proxies for a stylized voice, not human judgments. Dispersion is mean cosine',
        'distance to the output centroid, including within-speaker variation.','',
        '| System | Word errors / words | WER | DNSMOS | Raw-target cosine | Dispersion |',
        '| --- | --- | --- | --- | --- | --- |']
    for r in csv.DictReader((ROOT/'results/voice/summary.csv').open()):
        if r['split']!='heldout':continue
        lines.append(f"| {r['system']} | {r['word_errors']} / {r['words']} | {float(r['wer'])*100:.3f}% | {float(r['dnsmos_ovrl']):.3f} | {float(r['cosine_raw_target']):.6f} | {float(r['embedding_dispersion']):.6f} |")
    lines += ['',
        '`v8` is the default DSP character. `consistency` is MeanVC2 plus the serial',
        'character transform. `cascade` is utterance-end ASR/TTS and `seed_reference`',
        'is an offline comparison; neither is a continuously streaming product mode.','',
        'Separate unfamiliar-speaker stress WER was 2/69 = 2.899% original,',
        '12/69 = 17.391% default and 30/69 = 43.478% neural. This was one speaker,',
        'prompt referenced, and is not pooled with the heldout results. The recordings',
        'and transcripts are withheld.','',
        'Three listeners rated 15 samples each. Default means of listener medians',
        'were 3.33 intelligibility, 3.33 consistency and 3.00 cleanliness. Zero of three',
        'listeners met the combined quality criterion. No listener records or free-text',
        'backgrounds are included. Aggregate values are transcribed from the original',
        'summary, not reaggregated from public responses here.','',
        '## Voice timing and resources','',
        'The measured driver DAC-minus-ADC timestamp deltas were 6.02/6.60/9.67 ms',
        'median/p95/max, with a range down to -5.67 ms. Negative driver deltas are',
        'timestamp semantics, not negative physical latency. The declared algorithmic',
        'allowance was 42 ms. Their sum is **48.02/48.60/51.67 ms, an estimate**,',
        'not measured microphone-to-output latency. An alternative sum using reported',
        'stream input/output latency gives 68.33 ms. Neither is a physical bound.','',
        'The historical ungated build had a separate 21-22 ms driver-plus-DSP estimate',
        'and a 20-40 ms phone interpretation. Neither applies to the gated default.','',
        'The neural mode uses 160 ms device packets before model startup and reservoir',
        'cadence costs. It misses the latency aim and remains noisy on a live microphone.',
        'A short callback compute time does not remove its packet/startup delay.','',
        '| Mode | Callback p99 | Peak RSS | Compute / audio | Deadline misses |',
        '| --- | --- | --- | --- | --- |']
    for r in csv.DictReader((ROOT/'results/voice/efficiency.csv').open()):
        lines.append(f"| {r['mode']} | {float(r['callback_p99_ms']):.6f} ms | {float(r['rss_peak_mib']):.2f} MiB | {float(r['rtf_compute']):.6f} | {r['deadline_misses']} |")
    soak=json.loads((ROOT/'results/voice/soak_summary.json').read_text())
    lines += ['',
        'These were quiet, hardware-free callback replays with both app modes resident.',
        'Only peak RSS was saved; startup, ADC/DAC and OS scheduling are excluded from',
        'callback compute. Local architecture has no mandatory cloud service; that is',
        'an architectural estimate, not measured billing or energy cost.','',
        f"The separate exclusive-mode soak ran {soak['stop_elapsed_seconds']:.3f} s,",
        f"{soak['blocks']:,} blocks, with zero recorded fault counters. It was mostly",
        'quiet/gated, not one hour of assessed continuous speech. Device recovery on',
        'the earlier build took 3.843-7.938 s including operator/jack-dialog time;',
        'that result does not establish gated speech quality during recovery.','',
        '## Scene timing','',
        'Nominal runs requested 24 seconds of an empty scene with a fixed 216,953-Gaussian',
        'real scan, fitted desk/box/mug and procedural floor/chair. Head cameras were',
        '384x240 at declared 20/20 Hz; wrists 256x256 at 10/8 Hz; recorder off. These',
        'are settings, not achieved rates. The public scan retains the original renderer inputs, but the short sampled',
        'RGB/state replay cannot reproduce these historical runs.','',
        'Both nominal p95 values are below the 150 ms capture-to-DOM aim. This is a',
        'host/browser proxy, not physical screen timing or scene-change response. All',
        'later timing runs are retained below, including misses and the input-generation',
        'run. Recorder-on pulse runs are separate from the live-only nominal.','',
        '| Run | Median | p95 | Maximum | Samples |',
        '| --- | --- | --- | --- | --- |']
    for p in sorted((ROOT/'results/scene').glob('*_raw.json')):
        r=json.loads(p.read_text())['stages_ms']['capture_dom']
        lines.append(f"| {p.stem.removesuffix('_raw')} | {r['median']:.2f} ms | {r['p95']:.2f} ms | {r['max']:.2f} ms | {r['n']} |")
    lines += ['',
        'The first nominal drew 212.12 FPS but only 21.34 Hz fresh geometry; the later',
        'nominal drew 207.23 FPS with 19.46 Hz fresh geometry. Redraw is not freshness.',
        'Later replay baseline and all eight replay robustness settings missed 150 ms.',
        'Two rejected pre-run attempts produced no timing data; no timing retries or',
        'best-of selection were used in those later measurements.','',
        '## Scene changes and command response','',
        '| Change | Recorded response | Interpretation |',
        '| --- | --- | --- |',
        '| Added mug LIVE | 1603.59 ms | Misses 300 ms aim |',
        '| Moved box LIVE | 13363.87 ms | Misses 300 ms aim |',
        '| Chair LIVE | 15872.95 ms | Misses 300 ms aim |',
        '| Old box suppression | 5376.87 ms; 5288.45 ms after adequate evidence | Misses 300 ms aim |',
        '| Removed mug suppression | 30.30 ms; -76.81 ms after adequacy | Separately sampled clocks; timing compliance undetermined |','',
        'LIVE response measures visibility to 25% observed surface support within 2 cm.',
        'The negative adequacy-relative value is not negative physical latency.',
        'Fusion improved changed-region F1 in the moved-box case but worsened it in',
        'the added-mug case and was nearly equal for the chair. It is not uniformly better.','',
        '| Command | Stage | p95 | Observed / issued | No response |',
        '| --- | --- | --- | --- | --- |']
    for p in sorted((ROOT/'results/scene').glob('*_pulse_scores.json')):
        r=json.loads(p.read_text())
        for stage,m in r['summary_ms'].items():
            val='null' if m['p95'] is None else f"{m['p95']:.2f} ms"
            lines.append(f"| {r['category']} | {stage} | {val} | {m['n']} / {r['issued_pulses']} | {m['no_response']} |")
    lines += ['',
        'The command window ended before the next command or after 0.95 s. Joint',
        'motion, changed head-left RGB and later geometry-DOM bookkeeping are separate',
        'stages. Arm camera/DOM results are null in every trial. They are not zero.',
        'The 150 ms capture-to-DOM aim is not a command-stage threshold.','',
        '## Limitations','',
        'No physical robot or onboard validation. Wrist depth and odometry are simulated.',
        'RGB phone replay cannot establish real depth fusion. Host/browser timing does',
        'not establish physical display latency. Quiet audio, unfamiliar speakers, weak',
        'default character similarity and slow scene-change response remain limitations.',
        'Historical raw data and some historical tooling are unavailable in this lean copy.','']
    return '\n'.join(lines)

def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
    text=render();target=ROOT/'docs/results.md'
    if a.check:
        assert target.read_text()==text,'Results page differs from retained tables'
        print('Results page matches retained numerical summaries; no benchmark rerun.')
    else:target.write_text(text,encoding='utf-8');print('Wrote docs/results.md')

if __name__=='__main__':main()
