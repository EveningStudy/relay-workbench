"""M1 native Windows per-camera capture acceptance."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["maniskill", "sapien"], default="maniskill")
    args = parser.parse_args()
    import sapien
    import sapien.render
    sapien.render.set_imgui_ini_filename(str(Path("cache/sapien_imgui.ini").resolve()))
    out = Path("data/logs/m1")
    out.mkdir(parents=True, exist_ok=True)
    env = None
    if args.backend == "maniskill":
        import gymnasium as gym
        import mani_skill.envs
        env = gym.make("PickCube-v1", obs_mode="none", sim_backend="cpu", render_backend="gpu", sensor_configs={"width": 640, "height": 480})
        env.reset(seed=7)
        sensor = next(iter(env.unwrapped._sensors.values()))
        sensor.capture()
        images = sensor.get_obs(rgb=True, depth=True, position=False, segmentation=False)
        rgb = images["rgb"].cpu().numpy().squeeze()
        depth = images["depth"].cpu().numpy().squeeze()
        Image.fromarray(rgb.astype(np.uint8)).save(out / "stock_rgb.jpg", quality=90)
        np.savez_compressed(out / "stock_depth.npz", depth=depth.astype(np.float16))
        scene = env.unwrapped.scene.sub_scenes[0]
    else:
        scene = sapien.Scene()
    scene.add_ground(0)
    scene.set_ambient_light([0.5, 0.5, 0.5])
    scene.add_directional_light([1, 1, -2], [2, 2, 2])
    b = scene.create_actor_builder()
    b.add_box_visual(half_size=[0.1] * 3, material=[0.1, 0.65, 0.85])
    b.add_box_collision(half_size=[0.1] * 3)
    box = b.build_static(name="smoke_box")
    box.pose = sapien.Pose([0, 0, 0.1])
    cam = scene.add_camera("individual", 640, 480, 1.1, 0.01, 10)
    from scipy.spatial.transform import Rotation
    # SAPIEN camera is x forward, y left, z up.
    pos = np.array([1., -1., 0.9])
    forward = np.array([0, 0, 0.1]) - pos
    forward /= np.linalg.norm(forward)
    left = np.cross([0, 0, 1], forward)
    left /= np.linalg.norm(left)
    rot = np.column_stack([forward, left, np.cross(forward, left)])
    q = Rotation.from_matrix(rot).as_quat(scalar_first=True)
    cam.entity.pose = sapien.Pose(pos, q)
    timings = []
    for i in range(105):
        start = time.time_ns()
        scene.update_render()
        cam.take_picture()
        color = cam.get_picture("Color")
        position = cam.get_picture("Position")
        if i >= 5:
            timings.append((time.time_ns() - start) / 1e6)
    rgb = np.clip(color[..., :3] * 255, 0, 255).astype(np.uint8)
    Image.fromarray(rgb).save(out / "individual_rgb.jpg", quality=90)
    np.savez_compressed(out / "individual_depth.npz", depth=(-position[..., 2]).astype(np.float16))
    result = {"backend": args.backend, "device": str(scene.render_system.device), "renders": len(timings), "resolution": [640, 480], "ms": {"median": float(np.median(timings)), "p95": float(np.percentile(timings, 95)), "max": max(timings)}, "raw_ms": timings, "rgb_std": float(rgb.std())}
    assert rgb.std() > 5, "Blank render"
    (out / f"{args.backend}.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    if env:
        env.close()


if __name__ == "__main__":
    main()
