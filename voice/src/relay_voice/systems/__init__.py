"""Causal block systems. State belongs to one stream, never shared across speakers."""
from .baseline import Baseline, Passthrough


def create_system(name, config=None):
    if name == "v8":
        from .noise_v8 import NoiseControlledV8
        return NoiseControlledV8(config)
    if name == "passthrough":
        return Passthrough()
    if name == "baseline":
        return Baseline()
    if name == "lpc":
        from .lpc_robot import LPCRobot
        return LPCRobot(config)
    if name in ("llvc", "knn320"):
        from .neural import LLVCHybrid, KNNReference
        return LLVCHybrid(config) if name == "llvc" else KNNReference(config)
    raise ValueError(f"Unknown or unavailable system: {name}")
