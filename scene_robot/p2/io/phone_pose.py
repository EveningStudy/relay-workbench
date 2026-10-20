"""Image-derived checkerboard pose, with no simulator-state dependency."""
import cv2
import numpy as np
import yaml
from pathlib import Path
from p2.io.calibrate import PATTERN, detect, read_square_size


def board_points():
    m=yaml.safe_load(Path('human_inputs/02_measurements.yaml').read_text())
    b=m['calibration_board'];s=read_square_size('human_inputs/04_phone_calibration')
    if abs(s-b['square_size_m'])>1e-6:raise ValueError('board.txt and measured board YAML disagree')
    xyz=np.zeros((70,3),np.float32)
    xyz[:,:2]=(np.mgrid[:10,:7].T.reshape(-1,2)+1)*s+np.array(b['near_left_corner_xy'])
    xyz[:,2]=m['desk']['height_z']+b['height_above_desk_m']
    return xyz


def estimate(gray,k,d,world_points=None):
    corners,reason=detect(gray)
    if corners is None:return None,reason
    # The displayed PNG starts with a black outer square. With 11 by 8
    # squares its half-turn has opposite parity, resolving the usual 180 ambiguity.
    model=np.mgrid[:10,:7].T.reshape(-1,2).astype(np.float32)
    points=board_points() if world_points is None else np.asarray(world_points,dtype=np.float32)
    if points.shape!=(70,3):raise ValueError('Expected 70 measured world-space board corners')
    candidates=[]
    grid=corners.reshape(7,10,2)
    # Detector image ordering can have either handedness. Resolve both reflections
    # with the physical above-desk constraint, then the half-turn with colour parity.
    for g in (grid,grid[::-1],grid[:,::-1],grid[::-1,::-1]):
        c=np.ascontiguousarray(g.reshape(-1,1,2));h,_=cv2.findHomography(model,c.reshape(-1,2))
        probes=cv2.perspectiveTransform(np.array([[[-.5,-.5],[.5,-.5]]],np.float32),h)[0];vals=[]
        for u,v in probes:
            x,y=int(round(u)),int(round(v));patch=gray[max(y-2,0):y+3,max(x-2,0):x+3]
            vals.append(float(np.median(patch)) if patch.size else 128)
        if vals[1]-vals[0]<30:continue
        ok,rv,tv=cv2.solvePnP(points,c,k,d,flags=cv2.SOLVEPNP_ITERATIVE)
        if not ok:continue
        r=cv2.Rodrigues(rv)[0];world=np.eye(4);world[:3,:3]=r.T;world[:3,3]=-r.T@tv[:,0]
        err=float(np.sqrt(np.mean(np.sum((cv2.projectPoints(points,rv,tv,k,d)[0]-c)**2,axis=2))))
        if err<=2.5 and world[2,3]>points[0,2]+.05:
            candidates.append({'T_world_camera':world.tolist(),'rms_px':err,'corners':c.reshape(-1,2).tolist()})
    if not candidates:return None,'poor_pose_or_ambiguous_orientation'
    return min(candidates,key=lambda p:p['rms_px']),None
