# Provenance and changes

Historical results were measured on the original build. This repository is a
renamed, curated copy with a new Git history. The private source revision was
`727ffe38e9810d063be105439ff115c548b9584e`.

The later kitchen-refresh audit found the source at
`ffff7c0f6ce7c181ff1142ea584e23ca89263e0f`. Its tree is identical to the recorded
revision and all 51,680 inventoried file hashes still match, but its HEAD does
not match the initial inventory. The reflog records a reset to `fix-author`.
This discrepancy is retained; the source was not reset or rewritten to repair it.

Package names, import prefixes, robot names, URDF paths, UI strings and metadata
were changed. Old freeze receipts no longer certify the source in this copy.
No original freeze manifest is used as a passing gate here. Lightweight tests and
new synthetic replay validate only their stated functional contracts.

## Changes made for this copy

- Root hashed CPU dependency lock, setup script and task launcher replace the
  historical per-project GPU environments. The default voxel map selects CPU.
- Vendored package metadata uses neutral names; upstream algorithm source is
  unchanged. The full original copyright and licence grants are retained.
- The owner approved the aligned kitchen scan and scan-derived tabletop texture.
  Packing retains all renderer-consumed float32 values without downsampling.
  Measured fitted primitive dimensions are retained; calibration photos and full
  raw episodes remain excluded. The short sampled RGB/state replay is a
  presentation excerpt and does not inherit historical benchmark claims.
- The owner approved only seconds 6-18 of a physical phone recording, silent,
  plus its GIF. Personal media has display permission and no reuse licence.
- Robot geometry is generated from the retained editable design. New recorder
  sessions use a generic operator label instead of a person's identity.
- Tests retain their original assertions for audio DSP, callbacks, metrics,
  streaming parity, camera transport, visibility, timestamps and UI behaviour.
  A small fixture sets each suite's working directory in the new root layout.
  The default audio replay uses generated signals instead of a private recording.
- Historical documentation builders, film editors, development experiment runners
  and unused comparison sources were left out. Their licence texts and attribution
  remain. Unsupported model paths are explicitly described as research source.
- Reference WAV containers were rewritten without ancillary metadata. Decoded
  samples for clips 02-10 are identical; the target embedding is byte-identical.
  The withheld clip remains part of the original embedding's provenance.

## Retained evidence

`results/voice` keeps the original numerical summary, efficiency table, soak
summary/segments and latency-by-build table. `results/scene` retains two nominal
summaries, the final scene-change receipt and all 13 later run summaries plus
per-pulse scores. Original local paths and branding strings inside summaries were
redacted or renamed; numerical values were not changed.

These are curated summaries and receipts, not a full raw experiment archive.
Long callback logs, browser traces, full source video frames, remaining private inputs,
converted speech corpora and neural weights are absent. Some historical scripts
and inputs were already missing in the source package. Re-running the quick start
does not regenerate historical WER, listening scores or scene benchmarks.

The source checkout and its Git metadata were treated as read-only. A local
before/after SHA-256 inventory checks the source files independently of this new
history. Private review records are kept outside this repository.
