# Verification

Checked on Windows x64 with Python 3.11.17. Default tests/replay use CPU and need
no neural checkpoint. Historical measurements were not rerun.

## Kitchen and camera refresh

| Check | Outcome | Scope |
| --- | --- | --- |
| `run.ps1 scene` | Passed | Restored 216,953 kitchen Gaussians and generated robot geometry. |
| Scan packing comparison | Exact equality | Original/restored centers, covariance, RGB and opacity arrays; tabletop decoded pixels also equal. |
| `run.ps1 test` | 69 passed | Original lightweight suites and synthetic default replay. |
| `run.ps1 smoke` | Passed | 48,000 audio samples; 80 camera frames, 20 joint and 20 odometry messages. |
| `run.ps1 cameras --speed 1` | Passed | Independent subscriber received 288 RGB frames (72 per robot camera), 240 joints and 233 odometry messages; no depth. |
| Operator + recorded replay | Passed | Edge showed all four 6 fps streams, moving joint state, stereo images and circular wrist views. Functional display check, no timing benchmark. |
| Scene GIF | Passed | 144 fully decoded frames, 24 seconds at 6 fps; actual Viser rendering of the kitchen prior and joint replay. |
| Camera and phone GIFs | Passed | 72 fully decoded frames / 12 seconds each; contact-sheet visual review. |
| Phone MP4 | Passed | Full decode; exactly 12 seconds, no audio or subtitle stream, no location metadata. |
| `python scripts/results.py --check` | Passed | Page matches retained summaries; no new benchmark. |

An initial 10x accelerated camera replay lost messages through the bounded
transport queues. At normal speed, all bundled messages reached the independent
subscriber. The archive contains 233 odometry samples, not 240; state sampling
is nominally 20 Hz and does not invent missing source samples. Normal-speed
receipt does not promise lossless delivery under accelerated load or prove
historical timing/geometry accuracy.

The separate 100-second operator check consumed 1,143 of 1,152 published frames
across four loops, with nine recorded per-camera queue overflows. All four
panels displayed images. This confirms functional display with freshness drops;
it does not establish lossless operator playback.

The browser check used the Computer Use browser API with Edge. The four camera
panels displayed the recorded images, and the UI received the corresponding
robot joint states. The public still below is a frame of the offline scan tour;
it is not a screenshot claiming live fusion performance.

![Kitchen prior with robot and camera layout](media/operator.png)

Pinned Viser/Three.js emits a nonfatal `computeBoundingSphere` diagnostic for an
instanced Gaussian quad with two-component positions. Earlier inspection found
no nonfinite position-buffer values. The scan remains visible. Upstream clock
deprecation and shader-precision warnings also remain; this is no clean-console
claim. During the sampled RGB replay the fusion map can suppress parts of the
prior because its fitted camera geometry differs from the scan; the GIFs do not
claim reconstruction improvement.

## Phone pose demonstration

The phone demo now pairs each approved RGB frame with its image-derived camera
position/orientation in the kitchen scan. The original checkerboard detector/PnP
is reused with explicit bundled world-space board points, avoiding private
calibration-photo paths. Its default private-input API remains compatible.
Historical camera intrinsics fitted to the video are scaled to the public clip.

Recomputing 72 samples at 6 fps gave 31 valid poses and 41 unavailable samples.
Valid rotations are orthonormal, camera positions lie above the board, and board
reprojection RMS ranges from 0.090 to 1.786 px. These are fit diagnostics on this
presentation excerpt, not independent world accuracy or a new benchmark. No
missing pose is interpolated. The current frustum is hidden on failure; the
history trail never connects across a failed sample.

The GIF contains 72 fully decoded frames and is exactly 12 seconds. The matching
MP4 fully decodes with no audio or subtitle stream and no location metadata.
The 69 lightweight tests, default smoke replay and retained-results check passed
again after the explicit-board-points API change. Both input and output are
limited to the approved original seconds 6-18. All personal derivatives retain
copyright with public display permission only.

Three normal-speed loops delivered all 216 RGB frames and 216 camera-pose status
messages to an independent subscriber, including 93 valid and 123 unavailable
poses. The operator consumed all 216 frames with zero recorded queue overflows.
Edge showed the textured phone frustum for a valid pose and hid it on detection
failure; the phone panel and RGB-only scan-projection diagnostic also displayed.

## Earlier setup and voice checks

The root setup previously installed a fresh venv using the hashed CPU lock;
`pip check` passed. Browser arm selection and STOP checks passed on the earlier
procedural example. The new kitchen replaces that example. An earlier concurrent
test attempt failed on a busy port; stopping the preview service restored the
69-test pass without changing product assertions.

The 33-second voice film uses approved VCTK p226_003_mic2 and p237_003_mic2 with
the default DSP. Source FLAC-to-WAV conversion preserved every decoded sample.
Full film video/audio decode passed. Spoken content is based on owner-approved
paired dataset transcripts, not an independent human listening audit. Attribution
is visible in the film and its source manifest. No owner speech is published.

The release audit checks case-insensitive whole words and identifier boundaries
in every Git-visible path/text file, decoded subtitles, archive entry paths/JSON,
NPZ headers, image/video/audio metadata and reachable commit metadata. It also
checks Chinese characters, LFS pointers and the 100 MB file limit. Private audit
terms and detailed receipts are kept outside the repository. Media captions and
representative frame contact sheets were reviewed; no OCR or independent speech
transcription is claimed.

The original source is read-only. Its separate before/after inventory covers
51,680 file hashes and the source HEAD. No historical result value was changed.
The latest comparison found all file hashes unchanged, but the source HEAD now
differs from the initial inventory: `ffff7c0f` versus `727ffe38`. Their Git trees
are identical. The source reflog records a reset to `fix-author`; an unchanged
source-history claim cannot be certified from that inventory. No corrective
write or reset was performed on the source during this refresh.

## What this does not verify

No physical microphone/output run, new listening study, WER evaluation, neural
model installation, full GPU simulation or historical benchmark was rerun. There
is no physical robot. The separate phone film shows RGB only. Simulated wrist
depth is absent from the small public replay, and USB RGB footage was not found.
Passing functional checks does not make original measurements results of this
renamed CPU setup.
