"""Command, observed joint motion, changed RGB and geometry-DOM timing chain."""
import json
from pathlib import Path
import cv2
import numpy as np
import pandas as pd


def run(folder):
    folder=Path(folder);ep=folder/'episode';browser=json.loads((folder/'browser.json').read_text());command=browser.get('command_ns')
    result={'command_ns':command,'joint_motion_ms':None,'first_changed_camera_capture_ms':None,'post_motion_geometry_dom_ms':None,
        'scope':'Scripted key pulse; observed joint base-y displacement >2mm, then head RGB mean absolute change >1 intensity against the pre-command image (stride8), then a geometry DOM batch carrying a later capture. Last item is a data-age proxy, not proof of physical display presentation or semantic object motion.'}
    if command is not None and (ep/'joint_states.parquet').exists():
        joints=pd.read_parquet(ep/'joint_states.parquet');before=joints[joints.t_ns<=command]
        if len(before):
            ref=before.iloc[-1];index=list(ref.names).index('base_y');y=float(ref.q[index]);moving=joints[(joints.t_ns>command)&joints.q.apply(lambda q:abs(float(q[index])-y)>.002)]
            if len(moving):
                t_joint=int(moving.iloc[0].t_ns);result['joint_motion_ms']=(t_joint-command)/1e6
                frames=pd.read_parquet(ep/'frames.parquet');head=frames[frames.cam_id=='head_left'].sort_values('t_capture_ns');pre=head[head.t_capture_ns<=command]
                if len(pre):
                    image=cv2.imread(str(ep/pre.iloc[-1].rgb))[::8,::8].astype(float)
                    for row in head[head.t_capture_ns>=t_joint].itertuples():
                        current=cv2.imread(str(ep/row.rgb))[::8,::8].astype(float);difference=float(np.abs(current-image).mean())
                        if difference>1:
                            result['first_changed_camera_capture_ms']=(row.t_capture_ns-command)/1e6;result['rgb_difference']=difference
                            shown=next((s for s in browser['samples'] if s['t_dom_ns']>=command and any(r['t_capture_ns']>=row.t_capture_ns for r in s['rows'])),None)
                            if shown:result['post_motion_geometry_dom_ms']=(shown['t_dom_ns']-command)/1e6
                            break
    (folder/'command_chain.json').write_text(json.dumps(result,indent=2));return result
