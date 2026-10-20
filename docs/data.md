# Data, media and clone policy

## Included

- Source, configuration, tests and procedural robot geometry.
- Small numerical result tables and receipts, with private paths removed.
- Eighteen approved synthetic reference WAVs: raw/character clips 02 through 10.
- The original fixed target embedding, unchanged. One original spoken reference
  is withheld; the embedding's ten-clip provenance is disclosed in the voice guide.
- Newly generated architecture art and a 24-second procedural robot animation.
- Two publicly licensed VCTK WAVs and a 33-second source/character comparison.
  No personal owner recordings.

## Excluded

The historical scan, fitted home meshes/textures, photos, phone videos, webcam and
OBS footage, the owner's voice recordings, human teleop episodes, listening materials,
all original films and original subtitles are excluded. **No personal file is
included or proposed for publication in this version.** There is no listener data
in this copy, including no private listener identities.

Reference clip 01 is absent in both raw and character form. Old film narration,
title cards and UI captures are not fixed by renaming files; both existing films
are left out. The new scene animation is silent, and the new voice film uses the two approved
VCTK clips with their published dataset transcripts. New image/video files contain no location metadata.

## Why no LFS

Clones contain only small, useful assets. No LFS filters or pointers are used and
no file over 100 MB is committed. Neural checkpoints, multi-gigabyte recordings,
long callback traces, repetitive captures, toolchains and caches do not belong in
every source checkout.

No private archive is linked or uploaded. If larger public examples are later
approved, a versioned GitHub Release can carry a separately downloadable archive,
checksum, licence and provenance manifest. A release asset needs the same media
and privacy review as a Git commit. There are currently no such releases.

Setup downloads Python packages separately; their installed size is not the
repository clone size. It includes CPU PyTorch for voxel-map tests/UI, not CUDA
wheels. The live simulator and neural models are optional separate installations.

## Third-party speech dataset

Historical heldout results use CSTR VCTK Corpus 0.92: Junichi Yamagishi,
Christophe Veaux and Kirsten MacDonald (2019), University of Edinburgh CSTR,
[DOI 10.7488/ds/2645](https://doi.org/10.7488/ds/2645), CC BY 4.0. Most of the corpus and
its historical converted/stress samples are not bundled. Only `p226_003_mic2`
and `p237_003_mic2` are included as metadata-free WAV containers and as DSP/video
adaptations, retaining CC BY 4.0 attribution and a record of changes in
`media/voice_sources.json`. No endorsement by speakers or corpus authors is
implied. The two speakers read the same standard elicitation sentence.
The nine published synthetic target
texts include the standard elicitation passage; they are generated speech, not
recordings of VCTK participants. Keep the retained full CC BY notice with any
future VCTK adaptations.
