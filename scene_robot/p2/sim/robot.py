"""Raw SAPIEN robot drives, kept out of the perception process."""
from pathlib import Path
import numpy as np
import yaml


class Robot:
    def __init__(self, scene):
        self.cfg = yaml.safe_load(Path("configs/robot.yaml").read_text())
        loader = scene.create_urdf_loader()
        loader.fix_root_link = True
        self.body = loader.load("assets/robot/relay.urdf")
        self.joints = self.body.get_active_joints()
        self.names = [j.name for j in self.joints]
        self.targets = np.array([self.cfg["initial"].get(n, 0.) for n in self.names], np.float32)
        self.body.set_qpos(self.targets)
        self.velocity = np.zeros(3)
        self.limits = self.body.get_qlimits()
        for j, target in zip(self.joints, self.targets):
            base = j.name.startswith("base_")
            j.set_drive_properties(0 if base else 1500, 120 if base else 100, 1500, "acceleration")
            j.set_drive_target(float(target))
        # Coincident virtual shoulder axes require explicit self-collision filtering.
        for link in self.body.links:
            for shape in link.collision_shapes:
                shape.set_collision_groups([1, 1, 1, 0])

    def step(self):
        for j, target in zip(self.joints, self.targets):
            if j.name.startswith("base_"):
                j.set_drive_velocity_target(float(self.velocity[["base_x", "base_y", "base_yaw"].index(j.name)]))
            else:
                j.set_drive_target(float(target))
        self.body.set_qf(self.body.compute_passive_force(gravity=True, coriolis_and_centrifugal=True))

    def set_target(self, name, value):
        if name in self.names:
            i = self.names.index(name)
            self.targets[i] = np.clip(value, *self.limits[i])

    def state(self):
        return self.names, self.body.get_qpos().copy()
