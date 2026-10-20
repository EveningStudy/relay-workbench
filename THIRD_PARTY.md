# Third-party attribution

The root Apache-2.0 licence covers original project work only. Existing grants,
copyright headers and notices remain with their respective components. No model
checkpoint, native runtime or Python wheel is redistributed. Only the two small
VCTK speech examples described below are redistributed from that corpus.

## Retained source

| Component | Authors / upstream | Terms and scope |
| --- | --- | --- |
| LLVC | [Koe AI](https://github.com/KoeAI/LLVC), code revision 1627c5d358cf | MIT; `voice/third_party/llvc/LICENSE`; packaging/import prefix renamed. |
| kNN-VC | Matthew Baas, Benjamin van Niekerk, Herman Kamper; [upstream](https://github.com/bshall/knn-vc) | MIT, including the upstream reflection-on-copyright clause; `voice/third_party/knn/LICENSE`. |
| MeanVC2 | Guobin Ma, Yuxuan Xia, Yuepeng Jiang, Dake Guo, Hanke Xie, Jingbin Hu, Yanbo Wang, Lei Xie, Pengcheng Zhu; [ASLP-lab](https://github.com/ASLP-lab/MeanVC2/tree/13acf84c1bf135ea5edad9c245b345289b06b33e) | Apache-2.0 README grant retained at `licenses/meanvc2/upstream_README.md`. Code revision 13acf84c1bf135ea5edad9c245b345289b06b33e; historical model revision 39cdd19522fe896c227da691314d9a0e3b995486. |
| Cached convolution ancestors | Yangang Cao / Causal-U-Net; Daniel Stoller / Seq-U-Net | MIT; full grants in `licenses/voice/licenses/causal_unet_mit.txt` and `seq_unet_mit.txt`. |
| WavLM / HiFi-GAN ancestors | Microsoft / Jungil Kong and collaborators | MIT; full grants in `licenses/voice/licenses/wavlm_mit.txt` and `hifigan_mit.txt`. |

Vendored packaging identifiers have a neutral prefix. The retained upstream source
has not been relicensed. Public-copy modifications are listed in
[provenance](docs/provenance.md).

## Data, references and historical evaluation

| Component | Credit | Terms / retained notices |
| --- | --- | --- |
| CSTR VCTK 0.92 | Junichi Yamagishi, Christophe Veaux, Kirsten MacDonald (2019), University of Edinburgh CSTR; [official record](https://doi.org/10.7488/ds/2645) | CC BY 4.0; full `licenses/voice/licenses/vctk.txt`. Two clips, p226_003_mic2 and p237_003_mic2, are bundled as metadata-free WAVs under `docs/media/`. The voice demo synchronizes their source audio and default-DSP adaptations with a waveform video. Both audio and video adaptations retain CC BY 4.0; provenance is in `docs/media/voice_sources.json`. The rest of the corpus and historical converted/stress/listening audio are excluded. |
| Kokoro-82M v1.0, af_heart | [hexgrad](https://huggingface.co/hexgrad/Kokoro-82M) | Apache-2.0 weights; nine synthetic raw clips plus their character adaptations are included, approved by the owner. |
| Kokoro ONNX | [thewh1teagle](https://github.com/thewh1teagle/kokoro-onnx) | MIT runtime; `licenses/voice/licenses/kokoro_onnx_mit.txt`. |
| Whisper large-v3 | OpenAI | Apache-2.0; used in historical scoring only, no weights bundled. |
| ECAPA speaker embeddings | SpeechBrain / VoxCeleb model | Apache-2.0; used in historical scoring only. |
| Finetuned speaker WavLM | Microsoft UniSpeech | CC BY-SA 3.0; original grant `licenses/voice/v9a/licenses/unispeech_LICENSE.txt`. No model bundled; retain share-alike obligations on adaptations. |
| DNSMOS P.835/P.808 | Chandan Reddy, Vishak Gopal, Ross Cutler / Microsoft DNS Challenge | CC BY 4.0 root grant retained in `licenses/voice/v9a/licenses/dns_root_LICENSE.txt`. Proxy metric, not human MOS. |
| Seed-VC isolated historical comparison | [Plachtaa](https://github.com/Plachtaa/seed-vc) | GPL-3.0; full grants retained in `licenses/seedvc/upstream/LICENSE` and `licenses/voice/v9a/licenses/seedvc_LICENSE`. Comparison source and weights excluded; never imported by the default app. |
| MeanVC v1 comparison | ASLP-lab | Apache-2.0; `licenses/meanvc1/upstream/LICENSE` and retained model/source grant. Source and models excluded. |
| Applio / RVC comparison | Applio contributors | MIT source and prerequisite-model grant retained in `licenses/rvc/upstream/LICENSE` and `licenses/voice/v9a/licenses/applio_LICENSE`. No trained weights or comparison source included. |
| ContentVec / RMVPE ancestors | Original upstream authors | MIT / Apache-2.0 notices retained under `licenses/voice/v9a/licenses/`. |
| Silero VAD rejected trial | snakers4 | MIT; `licenses/voice/v9c/licenses/silero_vad_LICENSE`. Not enabled in the default. |
| eSpeak NG / phonemizer | Respective upstream contributors | GPL native/dependency components; `licenses/voice/licenses/espeak_ng_gpl3.txt`; no executable bundled. |

The target embedding was computed from ten original synthetic clips. One spoken
clip is withheld; the vector is unchanged. The new voice demonstration uses the two approved VCTK recordings and their
default DSP adaptations. Attribution and changes appear both on screen and in
the source manifest. No personal owner voice recording is included.

## Scene, robot and tooling

RealityFusion inspired the fixed-prior/live-observation approach; no code or
assets were copied from it. Credit: [upstream project](https://github.com/uhhhci/RealityFusion),
[paper](https://arxiv.org/abs/2408.01225).

ManiSkill and SAPIEN are Apache-2.0; full notices are retained in
`licenses/scene/maniskill_LICENSE` and `sapien_LICENSE.txt`. The optional simulator
uses SAPIEN directly. The procedural robot, public desk, evidence masks, camera
timing, teleop and recording adapters are project work.

Viser, OpenCV, NumPy/SciPy, trimesh, yourdfpy, plyfile, ZeroMQ/msgpack,
PyArrow/pandas, PyYAML, Pillow, psutil, PyTorch and pytest retain their installed
distribution licences. The hashed dependency lock identifies the packages used
by this copy. Optional GPU, neural and camera-import dependencies are separate.

`pi-heif` source is BSD-3-Clause; its historical Windows wheel bundles LGPLv3
components. The original source/bundled notices remain under `licenses/scene/`.
The public example does not need HEIC decoding.

imageio-ffmpeg is BSD. The FFmpeg executable used to make the new comparison is
GPLv3-or-later with libx264; the historical binary/configuration notice is retained
at `licenses/scene/ffmpeg_binary_licence.txt`. No FFmpeg binary is committed.
uv is MIT OR Apache-2.0; CPython uses its PSF licence. Neither toolchain is bundled.

Codex assisted with code, tests, evaluation tooling, procedural geometry,
documentation and editing. Synthetic public media is labelled. No human judgment,
physical recording or experimental measurement was generated by AI.
