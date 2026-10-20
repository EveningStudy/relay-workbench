"""Read only recorded observations/state. Evaluation truth is not opened here."""
import json
from pathlib import Path
import cv2
import numpy as np
import pandas as pd
from p2.msgs import CameraFrame,JointState,Odom


def read_frame(root,row,cameras=None):
    rgb=cv2.cvtColor(cv2.imread(str(Path(root)/row['rgb'])),cv2.COLOR_BGR2RGB);depth=None
    if isinstance(row.get('depth'),str) and row['depth'] not in ('','None'):
        depth=np.load(Path(root)/row['depth'])['depth'].astype(np.float32)
    h,w=rgb.shape[:2]
    if cameras and row['cam_id'] in cameras:
        c=cameras[row['cam_id']];w,h=c['width'],c['height'];rgb=cv2.resize(rgb,(w,h),interpolation=cv2.INTER_AREA)
        if depth is not None:depth=cv2.resize(depth,(w,h),interpolation=cv2.INTER_NEAREST)
    timing=json.loads(row.get('timing','{}')) if isinstance(row.get('timing'),str) else {}
    return CameraFrame(row['cam_id'],int(row['seq']),int(row['t_capture_ns']),int(row['t_send_ns']),str(row['source']),row['model'],w,h,rgb,depth,row['depth_kind'],timing)


def events(root):
    root=Path(root);items=[]
    for filename,kind in [('joint_states','joints'),('odom','odom'),('frames','frame')]:
        path=root/(filename+'.parquet')
        if not path.exists():continue
        for row in pd.read_parquet(path).to_dict('records'):
            t=int(row['t_capture_ns'] if kind=='frame' else row['t_ns'])
            if kind=='frame' and row['cam_id']=='external':continue
            items.append((t,{'joints':0,'odom':1,'frame':2}[kind],kind,row))
    return sorted(items,key=lambda x:(x[0],x[1]))


def replay_schedule(items,timing='recorded_send'):
    """Keep capture epochs while releasing delayed images at recorded send time.

    State messages retain their source timestamp. Recorder receipt is deliberately
    not used: it includes another subscriber's queue and disk workload.
    """
    if timing not in ('capture','recorded_send'):
        raise ValueError('Unknown replay timing: '+timing)
    scheduled=[]
    for capture,priority,kind,row in items:
        delivery=max(capture,int(row['t_send_ns'])) if kind=='frame' and timing=='recorded_send' else capture
        scheduled.append((delivery,priority,kind,row,capture))
    return sorted(scheduled,key=lambda item:(item[0],item[1]))


def state(kind,row,t_ns=None):
    t=int(row['t_ns'] if t_ns is None else t_ns)
    return JointState(t,list(row['names']),np.asarray(row['q'],np.float64)) if kind=='joints' else Odom(t,np.asarray(row['pose'],np.float64))
