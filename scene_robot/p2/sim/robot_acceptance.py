"""M2 drive every required axis and save a simulator rendering."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
import sapien
from p2.sim.robot import Robot
from p2.robot.fk import Kinematics


def main():
    scene = sapien.Scene()
    scene.set_timestep(1/120)
    scene.add_ground(0)
    scene.set_ambient_light([0.4]*3)
    scene.add_directional_light([1, 1, -2], [2]*3)
    robot = Robot(scene)
    before = robot.body.get_qpos().copy()
    fk = Kinematics()
    errors=[]
    for i in range(960):
        robot.velocity = np.array([0.05*np.cos(i/80), 0.05*np.sin(i/80), 0.05])
        for name in robot.names:
            if not name.startswith("base_"):
                robot.set_target(name, robot.cfg["initial"].get(name, 0.)+0.08*np.sin(i/80))
        robot.step()
        scene.step()
        q = robot.body.get_qpos()
        assert np.isfinite(q).all() and abs(q).max() < 15
        if i % 120 == 0:
            names,q=robot.state()
            p = fk.pose("head_cam_left", names, q)
            link=next(x for x in robot.body.links if x.name == "head_cam_left")
            errors.append(float(np.linalg.norm(p[:3,3]-link.pose.p)))
    cam = scene.add_camera("turntable", 800, 800, 1.0, 0.01, 10)
    from scipy.spatial.transform import Rotation
    pos = np.array([2.1, -2.4, 1.7])
    forward = np.array([0.6,-0.75,0.7])-pos
    forward/=np.linalg.norm(forward)
    left=np.cross([0,0,1],forward);left/=np.linalg.norm(left)
    cam.entity.pose=sapien.Pose(pos,Rotation.from_matrix(np.column_stack([forward,left,np.cross(forward,left)])).as_quat(scalar_first=True))
    scene.update_render();cam.take_picture()
    rgb=np.clip(cam.get_picture("Color")[...,:3]*255,0,255).astype(np.uint8)
    Image.fromarray(rgb).save("docs/evidence/relay_turntable.png")
    result={"steps":960,"finite":True,"max_fk_position_error_m":max(errors),"joint_names":robot.names,"start_q":before.tolist(),"end_q":q.tolist()}
    Path("docs/evidence/m2_robot.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
