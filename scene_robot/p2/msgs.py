"""Only runtime transport contract: msgpack headers plus raw array buffers."""
from dataclasses import dataclass, fields, field
import msgpack
import numpy as np


@dataclass
class CameraFrame:
    cam_id: str
    seq: int
    t_capture_ns: int
    t_send_ns: int
    source: str
    model: str
    width: int
    height: int
    rgb: np.ndarray
    depth: np.ndarray | None
    depth_kind: str
    timing: dict = field(default_factory=dict)


@dataclass
class JointState:
    t_ns: int
    names: list
    q: np.ndarray


@dataclass
class Odom:
    t_ns: int
    pose: np.ndarray


@dataclass
class Command:
    t_ns: int
    action: str
    values: dict


@dataclass
class Status:
    t_ns: int
    values: dict


@dataclass
class DisplayEvidence:
    t_ns: int
    flush_seq: int
    points: np.ndarray
    old_states: np.ndarray
    coverage: np.ndarray
    unknown: np.ndarray
    hit_ns: np.ndarray
    # Optional display-only pixels. Core voxel-state gate remains unchanged.
    # None distinguishes a historical recording from a genuinely empty layer.
    live_depth_points: np.ndarray | None = None
    live_depth_capture_ns: np.ndarray | None = None


TYPES = {c.__name__: c for c in (CameraFrame, JointState, Odom, Command, Status, DisplayEvidence)}


def encode(topic, message):
    if isinstance(message,CameraFrame):
        allowed={'t_render_ns','t_encode_ns','replay_decode_not_render'}
        if set(message.timing)-allowed:raise ValueError('Camera timing contains fields outside the operating contract')
    header = {"type": type(message).__name__, "fields": {}, "arrays": {}}
    buffers = []
    for f in fields(message):
        v = getattr(message, f.name)
        if isinstance(v, np.ndarray):
            a = np.ascontiguousarray(v)
            header["arrays"][f.name] = {"dtype": a.dtype.str, "shape": a.shape, "index": len(buffers)}
            buffers.append(a.tobytes())
        else:
            header["fields"][f.name] = v
    return [topic.encode(), msgpack.packb(header, use_bin_type=True), *buffers]


def decode(parts):
    header = msgpack.unpackb(parts[1], raw=False)
    data = header["fields"]
    for key, spec in header["arrays"].items():
        data[key] = np.frombuffer(parts[2+spec["index"]], dtype=spec["dtype"]).reshape(spec["shape"]).copy()
    return parts[0].decode(), TYPES[header["type"]](**data)
