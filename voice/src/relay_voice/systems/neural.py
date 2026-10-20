"""Audited fixed-chunk experiments. Models are excluded from Git."""
import importlib
import json
from pathlib import Path
import shutil
import sys
import numpy as np
import torch
from .lpc_robot import LPCRobot

_LLVC = None
_KNN = None


def llvc_model():
    global _LLVC
    if _LLVC is None:
        import relay_llvc_vendor
        sys.path.insert(0, str(Path(relay_llvc_vendor.__file__).parent))
        module = importlib.import_module("relay_llvc_vendor.model")
        config = json.loads(Path("data/models/llvc/config.json").read_text())
        model = module.Net(**config["model_params"])
        checkpoint = torch.load("data/models/llvc/models/checkpoints/llvc/G_500000.pth", map_location="cpu", weights_only=True)
        model.load_state_dict(checkpoint["model"])
        model.eval()
        _LLVC = model
    return _LLVC


def knn_model():
    global _KNN
    if _KNN is None:
        import relay_knn_vendor
        root = Path(relay_knn_vendor.__file__).parent
        cache = Path(torch.hub.get_dir())/"checkpoints"
        cache.mkdir(parents=True, exist_ok=True)
        for name in ["WavLM-Large.pt", "prematch_g_02500000.pt"]:
            if not (cache/name).exists():
                shutil.copyfile(Path("data/models/knn")/name, cache/name)
        model = torch.hub.load(str(root), "knn_vc", source="local", pretrained=True,
                               prematched=True, device="cuda")
        from scipy.signal import resample_poly
        import soundfile as sf
        reference = []
        for path in sorted(Path("data/reference").glob("tts_raw_*.wav")):
            raw, sr = sf.read(path, dtype="float32")
            assert sr == 24000
            reference.append(torch.from_numpy(resample_poly(raw, 2, 3).astype(np.float32))[None])
        matching = model.get_matching_set(reference, vad_trigger_level=0)
        _KNN = (model, matching)
    return _KNN


class FixedChunk:
    """Finite intrinsic model assembly and playout storage, never catch-up queues.

    All inference happens synchronously on the callback thread. Output advances
    one block per call even if the engine discards a late block. The arrays have
    constant size for the life of the stream.
    """
    def setup(self, chunk_samples, initial_blocks, config):
        self.chunk_samples = chunk_samples
        self.input = np.zeros(chunk_samples, dtype=np.float32)
        self.filled = 0
        self.output = np.zeros(chunk_samples*3, dtype=np.float32)
        self.read_pos, self.write_pos, self.count = 0, 0, 0
        self.initial_blocks = initial_blocks
        self.robot = LPCRobot(config)

    def process_block(self, x16k):
        assert len(x16k) == 80
        source_pos = 0
        while source_pos < 80:
            n = min(80-source_pos, self.chunk_samples-self.filled)
            self.input[self.filled:self.filled+n] = x16k[source_pos:source_pos+n]
            self.filled += n
            source_pos += n
            if self.filled == self.chunk_samples:
                result = self.infer(self.input.copy())
                if len(result) != self.chunk_samples:
                    raise ValueError("Neural model changed chunk duration")
                if self.count+len(result) > len(self.output):
                    raise RuntimeError("Fixed model playout capacity exceeded")
                indices = (self.write_pos+np.arange(len(result)))%len(self.output)
                self.output[indices] = result
                self.write_pos = (self.write_pos+len(result))%len(self.output)
                self.count += len(result)
                self.filled = 0
        if self.initial_blocks:
            self.initial_blocks -= 1
            return self.robot.process_block(np.zeros(80, dtype=np.float32))
        if self.count < 80:
            raise RuntimeError("Fixed model playout underrun; no catch-up permitted")
        result = self.output[(self.read_pos+np.arange(80))%len(self.output)].copy()
        self.read_pos = (self.read_pos+80)%len(self.output)
        self.count -= 80
        return self.robot.process_block(result)


class LLVCHybrid(FixedChunk):
    name = "llvc"
    # Fixed assembly 20ms plus unshifted upstream lookahead alignment 1ms.
    algorithmic_delay_ms = 21.0

    def __init__(self, config=None):
        torch.set_num_threads(1)
        self.model = llvc_model()
        self.buffers = self.model.init_buffers(1, torch.device("cpu"))
        self.convctx = self.model.convnet_pre.init_ctx_buf(1, torch.device("cpu"))
        self.context = np.zeros(self.model.L*2, dtype=np.float32)
        self.setup(self.model.L*self.model.dec_chunk_size, 4, config)

    @torch.inference_mode()
    def infer(self, audio):
        tensor = torch.from_numpy(np.r_[self.context, audio])[None, None]
        result, *state = self.model(tensor, *self.buffers, self.convctx, pad=False)
        self.buffers, self.convctx = tuple(state[:3]), state[3]
        self.context = audio[-len(self.context):].copy()
        return result.squeeze().cpu().numpy().astype(np.float32)


class KNNReference(FixedChunk):
    name = "knn320"
    algorithmic_delay_ms = 320.0

    def __init__(self, config=None):
        self.model, self.matching = knn_model()
        self.config_path = config
        self.setup(5120, 64, config)

    @torch.inference_mode()
    def infer(self, audio):
        features = self.model.get_features(torch.from_numpy(audio)[None], vad_trigger_level=0)
        result = self.model.match(features, self.matching, topk=4, tgt_loudness_db=None,
                                  target_duration=len(audio)/16000)
        return result.cpu().numpy().astype(np.float32)

    @torch.inference_mode()
    def convert_utterance(self, audio16):
        raw = self.infer(audio16)
        robot = LPCRobot(self.config_path)
        padded = np.pad(raw, (0, (-len(raw))%80))
        output = np.concatenate([robot.process_block(padded[i:i+80]) for i in range(0, len(padded), 80)])
        return output[:len(raw)]
