# Results

Historical measurements below belong to the original build. This renamed copy
does not inherit its freeze hashes. Retained CSV/JSON summaries are under
`results/`; full raw recordings, models and long telemetry are not bundled.
Run `python scripts/results.py --check` to verify this page against the retained
tables. That checks transcription and arithmetic, not new inference or hardware.

## Voice quality

Twelve heldout speakers, five clips each, mostly read English. EER measures
source-identity discrimination. DNSMOS and embedding similarity are imperfect
proxies for a stylized voice, not human judgments. Dispersion is mean cosine
distance to the output centroid, including within-speaker variation.

| System | Word errors / words | WER | DNSMOS | Raw-target cosine | Dispersion |
| --- | --- | --- | --- | --- | --- |
| baseline | 7 / 828 | 0.845% | 1.412 | -0.036267 | 0.429859 |
| cascade | 3 / 828 | 0.362% | 3.421 | 0.859088 | 0.124445 |
| consistency | 43 / 828 | 5.193% | 3.054 | 0.341968 | 0.160313 |
| original | 2 / 828 | 0.242% | 3.239 | 0.073020 | 0.583242 |
| seed_reference | 140 / 828 | 16.908% | 3.033 | 0.163609 | 0.207245 |
| v8 | 7 / 828 | 0.845% | 2.402 | 0.040559 | 0.344517 |

`v8` is the default DSP character. `consistency` is MeanVC2 plus the serial
character transform. `cascade` is utterance-end ASR/TTS and `seed_reference`
is an offline comparison; neither is a continuously streaming product mode.

Separate unfamiliar-speaker stress WER was 2/69 = 2.899% original,
12/69 = 17.391% default and 30/69 = 43.478% neural. This was one speaker,
prompt referenced, and is not pooled with the heldout results. The recordings
and transcripts are withheld.

Three listeners rated 15 samples each. Default means of listener medians
were 3.33 intelligibility, 3.33 consistency and 3.00 cleanliness. Zero of three
listeners met the combined quality criterion. No listener records or free-text
backgrounds are included. Aggregate values are transcribed from the original
summary, not reaggregated from public responses here.

## Voice timing and resources

The measured driver DAC-minus-ADC timestamp deltas were 6.02/6.60/9.67 ms
median/p95/max, with a range down to -5.67 ms. Negative driver deltas are
timestamp semantics, not negative physical latency. The declared algorithmic
allowance was 42 ms. Their sum is **48.02/48.60/51.67 ms, an estimate**,
not measured microphone-to-output latency. An alternative sum using reported
stream input/output latency gives 68.33 ms. Neither is a physical bound.

The historical ungated build had a separate 21-22 ms driver-plus-DSP estimate
and a 20-40 ms phone interpretation. Neither applies to the gated default.

The neural mode uses 160 ms device packets before model startup and reservoir
cadence costs. It misses the latency aim and remains noisy on a live microphone.
A short callback compute time does not remove its packet/startup delay.

| Mode | Callback p99 | Peak RSS | Compute / audio | Deadline misses |
| --- | --- | --- | --- | --- |
| v8 | 0.650223 ms | 933.21 MiB | 0.062562 | 0 |
| consistency | 64.509592 ms | 969.87 MiB | 0.242773 | 0 |

These were quiet, hardware-free callback replays with both app modes resident.
Only peak RSS was saved; startup, ADC/DAC and OS scheduling are excluded from
callback compute. Local architecture has no mandatory cloud service; that is
an architectural estimate, not measured billing or energy cost.

The separate exclusive-mode soak ran 3600.093 s,
719,985 blocks, with zero recorded fault counters. It was mostly
quiet/gated, not one hour of assessed continuous speech. Device recovery on
the earlier build took 3.843-7.938 s including operator/jack-dialog time;
that result does not establish gated speech quality during recovery.

## Scene timing

Nominal runs requested 24 seconds of an empty scene with a fixed 216,953-Gaussian
real scan, fitted desk/box/mug and procedural floor/chair. Head cameras were
384x240 at declared 20/20 Hz; wrists 256x256 at 10/8 Hz; recorder off. These
are settings, not achieved rates. The public scan retains the original renderer inputs, but the short sampled
RGB/state replay cannot reproduce these historical runs.

Both nominal p95 values are below the 150 ms capture-to-DOM aim. This is a
host/browser proxy, not physical screen timing or scene-change response. All
later timing runs are retained below, including misses and the input-generation
run. Recorder-on pulse runs are separate from the live-only nominal.

| Run | Median | p95 | Maximum | Samples |
| --- | --- | --- | --- | --- |
| baseline_01 | 113.14 ms | 164.24 ms | 212.56 ms | 458 |
| bias_100_01 | 88.57 ms | 156.22 ms | 198.16 ms | 459 |
| bias_50_01 | 95.36 ms | 150.99 ms | 192.04 ms | 459 |
| input_02 | 88.99 ms | 138.96 ms | 182.71 ms | 738 |
| loss_10_01 | 111.21 ms | 165.33 ms | 201.28 ms | 437 |
| loss_30_01 | 108.64 ms | 158.14 ms | 321.77 ms | 399 |
| nominal_live_01 | 89.06 ms | 136.86 ms | 163.84 ms | 743 |
| nominal | 75.33 ms | 120.19 ms | 162.53 ms | 775 |
| outage_2s_01 | 115.63 ms | 165.77 ms | 184.93 ms | 438 |
| pulse_arm_01 | 99.80 ms | 153.00 ms | 214.74 ms | 705 |
| pulse_drive_01 | 104.85 ms | 159.88 ms | 196.79 ms | 697 |
| pulse_head_01 | 101.17 ms | 158.66 ms | 194.68 ms | 696 |
| stereo_100_01 | 105.78 ms | 155.27 ms | 229.03 ms | 371 |
| stereo_50_01 | 105.61 ms | 154.75 ms | 206.17 ms | 370 |

The first nominal drew 212.12 FPS but only 21.34 Hz fresh geometry; the later
nominal drew 207.23 FPS with 19.46 Hz fresh geometry. Redraw is not freshness.
Later replay baseline and all eight replay robustness settings missed 150 ms.
Two rejected pre-run attempts produced no timing data; no timing retries or
best-of selection were used in those later measurements.

## Scene changes and command response

| Change | Recorded response | Interpretation |
| --- | --- | --- |
| Added mug LIVE | 1603.59 ms | Misses 300 ms aim |
| Moved box LIVE | 13363.87 ms | Misses 300 ms aim |
| Chair LIVE | 15872.95 ms | Misses 300 ms aim |
| Old box suppression | 5376.87 ms; 5288.45 ms after adequate evidence | Misses 300 ms aim |
| Removed mug suppression | 30.30 ms; -76.81 ms after adequacy | Separately sampled clocks; timing compliance undetermined |

LIVE response measures visibility to 25% observed surface support within 2 cm.
The negative adequacy-relative value is not negative physical latency.
Fusion improved changed-region F1 in the moved-box case but worsened it in
the added-mug case and was nearly equal for the chair. It is not uniformly better.

| Command | Stage | p95 | Observed / issued | No response |
| --- | --- | --- | --- | --- |
| arm | joint_motion_ms | 134.46 ms | 20 / 20 | 0 |
| arm | first_changed_camera_capture_ms | null | 0 / 20 | 20 |
| arm | post_motion_geometry_dom_ms | null | 0 / 20 | 20 |
| drive | joint_motion_ms | 31.92 ms | 20 / 20 | 0 |
| drive | first_changed_camera_capture_ms | 117.86 ms | 20 / 20 | 0 |
| drive | post_motion_geometry_dom_ms | 256.13 ms | 20 / 20 | 0 |
| head | joint_motion_ms | 51.47 ms | 20 / 20 | 0 |
| head | first_changed_camera_capture_ms | 170.85 ms | 20 / 20 | 0 |
| head | post_motion_geometry_dom_ms | 342.77 ms | 20 / 20 | 0 |

The command window ended before the next command or after 0.95 s. Joint
motion, changed head-left RGB and later geometry-DOM bookkeeping are separate
stages. Arm camera/DOM results are null in every trial. They are not zero.
The 150 ms capture-to-DOM aim is not a command-stage threshold.

## Limitations

No physical robot or onboard validation. Wrist depth and odometry are simulated.
RGB phone replay cannot establish real depth fusion. Host/browser timing does
not establish physical display latency. Quiet audio, unfamiliar speakers, weak
default character similarity and slow scene-change response remain limitations.
Historical raw data and some historical tooling are unavailable in this lean copy.
