"""FK derives only from static URDF and observed joint states."""
import numpy as np
import yourdfpy


class Kinematics:
    def __init__(self, path="assets/robot/relay.urdf"):
        self.urdf = yourdfpy.URDF.load(path, load_meshes=False, build_scene_graph=True)
        self.names = list(self.urdf.actuated_joint_names)

    def pose(self, frame, names, q):
        self.urdf.update_cfg(dict(zip(names, q)))
        return np.asarray(self.urdf.get_transform(frame), dtype=np.float64)
