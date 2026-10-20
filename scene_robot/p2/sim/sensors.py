"""Render camera observations only; transforms come from the mounted links."""
import numpy as np
import sapien
from p2.sim.fisheye import CubeRemap, FACE_ROTATIONS

OPTICAL_FROM_SAPIEN = np.array([[0,-1,0],[0,0,-1],[1,0,0]])


class Sensor:
    def __init__(self,scene,robot,cam_id,cfg):
        self.scene,self.cfg,self.cam_id=scene,cfg,cam_id
        self.link=next(l for l in robot.body.links if l.name==cfg["frame"])
        self.cameras=[];self.seq=0
        if cfg["model"]=="kb4":
            self.remap=CubeRemap(cfg["width"],cfg["cube_size"],cfg["kb4"])
            rotations=FACE_ROTATIONS;w=h=cfg["cube_size"];fovy=np.pi/2
        else:
            self.remap=None;rotations=[np.eye(3)];w,h=cfg["width"],cfg["height"]
            fx=w/(2*np.tan(np.deg2rad(cfg["horizontal_fov_deg"])/2));fovy=2*np.arctan(h/(2*fx))
        for i,rotation in enumerate(rotations):
            camera=scene.add_camera(f"{cam_id}_{i}",w,h,fovy,0.03,8.)
            t=np.eye(4);t[:3,:3]=rotation@OPTICAL_FROM_SAPIEN
            self.cameras.append((camera,t))

    def capture(self):
        pose=self.link.pose.to_transformation_matrix()
        for cam,t in self.cameras: cam.entity.pose=sapien.Pose(pose@t)
        self.scene.update_render()
        rgbs=[];distances=[]
        for cam,_ in self.cameras:
            cam.take_picture();rgb=cam.get_picture("Color");packed=cam.get_picture("PositionSegmentation")
            pos=packed[...,:3].astype(np.float32)/1000
            rgbs.append(rgb[...,:3].copy())
            depth=-pos[...,2]
            if self.remap:
                depth=np.linalg.norm(pos[...,:3],axis=-1)
            depth[~np.isfinite(depth)|(depth>7.9)|(depth<0.03)]=0
            distances.append(depth.astype(np.float32))
        return self.remap.apply(rgbs,distances) if self.remap else (rgbs[0],distances[0])
