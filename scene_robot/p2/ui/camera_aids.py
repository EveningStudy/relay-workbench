"""Small calibrated view outlines at received capture-time FK poses."""
import numpy as np
from scipy.spatial.transform import Rotation

PALETTE={'head_left':(30,180,255),'wrist_left':(255,160,20),'wrist_right':(255,60,170)}


def update(server,tf,latest,cameras,handles):
    for cam,color in PALETTE.items():
        name='/camera_aids/'+cam
        if cam not in latest:continue
        frame,_=latest[cam]
        try:pose,_=tf.pose(cameras[cam]['frame'],frame.t_capture_ns)
        except LookupError:
            for handle in handles.get(cam,[]):handle.visible=False
            continue
        cfg=cameras[cam];origin=pose[:3,3];rotation=pose[:3,:3];parts=[]
        quaternion=Rotation.from_matrix(rotation).as_quat(scalar_first=True)
        if cam in handles:
            outline,label=handles[cam]
            # Pinned viser property setters skip unchanged transforms. Keep the
            # calibrated local hemisphere and text instead of rebuilding nodes.
            outline.position=origin;outline.wxyz=quaternion;outline.visible=True
            # The label is a child of the transformed outline, so its offset
            # is local. Applying the world pose here would transform it twice.
            label.visible=True
            continue
        if cfg['model']=='kb4':
            # A hemisphere, not a pinhole approximation to a 180-degree lens.
            segments=[]
            for phi in np.arange(0,2*np.pi,np.pi/4):
                theta=np.linspace(0,np.pi/2,13);arc=np.c_[np.sin(theta)*np.cos(phi),np.sin(theta)*np.sin(phi),np.cos(theta)]*.22
                segments.extend(np.stack([arc[:-1],arc[1:]],axis=1))
            theta=np.linspace(0,2*np.pi,33);rim=np.c_[np.cos(theta),np.sin(theta),np.zeros(len(theta))]*.22
            segments.extend(np.stack([rim[:-1],rim[1:]],axis=1));segments=np.array(segments)
            parts.append(server.scene.add_line_segments(name,segments,color,thickness=1.5,thickness_units='screen',position=origin,wxyz=quaternion))
        else:
            fx=cfg['width']/(2*np.tan(np.deg2rad(cfg['horizontal_fov_deg'])/2));fov=2*np.arctan(cfg['height']/(2*fx))
            parts.append(server.scene.add_camera_frustum(name,fov=fov,aspect=cfg['width']/cfg['height'],scale=.22,color=color,
                thickness=1.5,thickness_units='screen',position=origin,wxyz=quaternion))
        parts.append(server.scene.add_label(name+'/label',cam.replace('_',' ')+' | '+('180 fisheye' if cfg['model']=='kb4' else 'head'),position=(0,0,.25),font_screen_scale=.8))
        handles[cam]=parts
