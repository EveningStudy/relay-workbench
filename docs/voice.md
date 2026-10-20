# Voice guide

Run the root setup and smoke commands first. The default needs no model, reference
audio, GPU or network service. Live microphone control is a Windows console app;
the microphone and output must share one physical audio clock.

```powershell
.\.venv\Scripts\python.exe -m sounddevice
.\run.ps1 voice --input 1 --output 3 --same-clock --seconds 60
```

Select actual device IDs. Use headphones to avoid feedback. For shared mode add
`--shared`. Telemetry goes to `voice/results/live.jsonl`, which is ignored by Git.
Default mode is `v8`; the identifier is retained so old numerical tables remain
readable. Bypass, simple baseline and the default are keys 1, 2 and 3.

## Offline processing

`voice/eval/convert.py` calls the same `Pipeline` as the live callback. The root
smoke script uses it on a generated harmonic probe. That signal checks finite,
bounded output and functional state; it is not a speech quality demonstration.

The [33-second comparison](media/voice_demo.mp4) uses two real VCTK speakers,
p226 and p237, reading the same sentence. For each speaker it plays the original
recording and then this repository's default DSP output, with a moving waveform.
No speech is trimmed or normalized; silence separates the four segments. This
is an illustrative example, not a new listening, identity or latency result.
The README embeds a GitHub-hosted player.

Rebuild it after root setup with:

```powershell
.\.venv\Scripts\python.exe scripts/make_voice_media.py
```

The two small source WAVs are bundled in `docs/media/`, with transcript, hashes,
changes and CC BY 4.0 attribution in `voice_sources.json`. FLAC containers were
converted to PCM WAV without changing decoded samples or retaining ancillary
metadata. No TTS voice, model download or personal owner recording is required.
The spoken-content review uses dataset transcripts explicitly approved by the
owner; it is not an independent listening audit.

## Synthetic target references

`voice/references/` contains nine raw Kokoro clips and nine corresponding character
adaptations under neutral names. `manifest.json` lists the exact text and decoded
sample hashes. WAV containers were rewritten without ancillary metadata; decoded
samples were checked for equality.

`target_embedding.npy` is byte-identical to the original target vector. It was
computed from the original **ten-clip** reference set. One clip is withheld because
it contains a placeholder name. No target was regenerated for this copy, and the
historical similarity results still refer to the original target.

## Optional neural research path

The audited MeanVC2 adapter is retained in `src/relay_voice/v9/meanvc_live.py` with
upstream runtime source in `third_party/meanvc2`. Its reference embedding points
to the retained vector; the unused reference-audio argument now points to a
published neutral clip. `--low-only` deliberately bypasses this model path.

Weights, training audio and experimental checkpoints are not distributed. Consult
the pinned upstream links in [THIRD_PARTY.md](../THIRD_PARTY.md) for model retrieval
and their own grants. The neural path additionally needs compatible torchaudio,
s3prl, x-transformers and model files in the upstream layout. This copy has **not**
revalidated a complete neural install or inference. Treat that path as research
source, not a second supported quick start.
