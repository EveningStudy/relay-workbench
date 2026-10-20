# Data, media and clone policy

## Included

- Source, configuration, tests and generated robot geometry.
- Small historical numerical result tables/receipts with private paths removed.
- Eighteen approved synthetic reference WAVs: raw/character clips 02 through 10.
- The unchanged fixed target embedding, computed from the original ten clips.
  Clip 01 is withheld because it contains a placeholder name.
- Two publicly licensed VCTK WAVs and a 33-second source/character comparison.
- The owner-approved kitchen scan, texture, short simulator replay and silent
  phone excerpt listed below. No personal owner speech or listener data.

## Exact personal-media publication scope

Copyright 2026 Zixin Wang. **All rights reserved.** The owner permits public
repository display of these assets; no licence to reuse the media is granted.
They are excluded from the root Apache-2.0 licence.

| Repository file | Published content |
| --- | --- |
| `scene_robot/assets/kitchen/prior.npz` | Aligned kitchen scan: all 216,953 Gaussians, 14 renderer-consumed fields; 8.36 MB. |
| `scene_robot/assets/kitchen/tabletop.png` | Scan-derived tabletop texture, RGB pixels retained, metadata removed. |
| `scene_robot/assets/kitchen/camera_replay.zip` | 12-second sampled simulator RGB/state excerpt; 360 metadata-free JPEGs across five streams, joints/odometry; 6.47 MB. Camera RGB uses the personal tabletop texture. |
| `scene_robot/assets/kitchen/manifest.json` | Scan/replay hashes, retained properties and publication scope. |
| `docs/media/scene.gif` | 24-second orbit of kitchen scan, robot joint replay and camera mounts. |
| `docs/media/cameras.gif` | 12-second stereo-head and two-wrist simulator RGB panel. |
| `docs/media/wrists.gif` | 12-second two-wrist simulator RGB panel. |
| `docs/media/phone.gif` | Silent GIF from original phone seconds 6-18 only. |
| `docs/media/phone_excerpt.mp4` | Same approved 12-second phone interval, silent, metadata removed. |
| `docs/media/operator.png` | Still from the kitchen scan demonstration. |
| `docs/media/scene_sources.json` | Derivation, hashes and exact permission boundaries. |

The aligned scan is packed without downsampling. Unused normals and higher-order
SH properties are omitted; all inputs consumed by the current renderer are
unchanged. The replay samples one exposure per 1/6-second bin from original
seconds 4-16 of a scripted simulator episode, with state sampled at 20 Hz.
This is a presentation excerpt, not a selected benchmark result. JPEGs are
re-encoded, so they are not claimed to be bit-identical source images.

## Excluded

Full phone recordings, calibration/other home photos, raw scan capture, unused
scan properties, physical USB footage, OBS films, original narrated films and
subtitles, owner voice, human teleop episodes and listening materials remain out.
No private listener identities or listener-level data is included. Reference clip
01 is absent in raw and character form. The old films visibly contain private
branding in title cards/browser UI and the voice narration contains it in speech;
renaming their files would not remove that content. They remain excluded.

The new scene/camera GIFs are silent. The phone MP4 has no audio stream. Voice demo
speech uses the two owner-approved VCTK transcripts, not inferred spoken content.
Published image/video containers carry no location metadata.

## Why no LFS

Useful runnable assets are packed into ordinary Git files under 100 MB. The scan
pack is 8.36 MB rather than the original 53.81 MB PLY; the short replay is 6.47 MB.
No LFS filters or pointers are used. Multi-gigabyte raw captures, checkpoints,
callback traces and caches are excluded. No private archive is linked or uploaded.
A future large approved dataset could be a separately downloadable GitHub Release
with a checksum, provenance and explicit licence; none is provided now.

Setup downloads Python packages separately; installed environment size is not
clone size. It includes CPU PyTorch, not CUDA wheels. GPU simulation and neural
models require separate optional installations.

## Third-party speech dataset

CSTR VCTK Corpus 0.92: Junichi Yamagishi, Christophe Veaux and Kirsten MacDonald
(2019), University of Edinburgh CSTR,
[DOI 10.7488/ds/2645](https://doi.org/10.7488/ds/2645), CC BY 4.0.
Only `p226_003_mic2` and `p237_003_mic2` are included as metadata-free WAVs and
DSP/video adaptations, retaining CC BY 4.0 attribution and recorded changes in
`media/voice_sources.json`. No speaker/author endorsement is implied. The nine
published synthetic target texts include the standard elicitation passage; those
are generated speech, not VCTK participant recordings. Keep the full CC BY notice
with VCTK adaptations. Historical heldout/stress corpora remain excluded.
