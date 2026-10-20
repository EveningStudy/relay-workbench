"""Small deterministic transport fixture; images are generated patterns, not a renderer."""
from pathlib import Path
import json
import cv2, numpy as np, pandas as pd, yaml

def generate(root,scene):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    (root/'rgb').mkdir(exist_ok=True);(root/'depth').mkdir(exist_ok=True)
    initial=yaml.safe_load((Path(scene)/'configs/robot.yaml').read_text())['initial']
    names=list(initial);q=list(initial.values());base=1_000_000_000
    frames=[];joints=[];odom=[]
    for i in range(20):
        t=base+i*50_000_000
        joints.append({'t_ns':t,'names':names,'q':q})
        odom.append({'t_ns':t,'pose':[initial['base_x'],initial['base_y'],initial['base_yaw']]})
        for n in ['head_left','head_right','wrist_left','wrist_right']:
            rgb=f'rgb/{n}_{i:03d}.png';depth=f'depth/{n}_{i:03d}.npz'
            img=np.full((64,96,3),30,np.uint8)
            cv2.rectangle(img,(i+10,15),(i+35,45),(180,130,50),-1)
            cv2.imwrite(str(root/rgb),img)
            np.savez_compressed(root/depth,depth=np.full((64,96),.65,np.float32))
            frames.append({'cam_id':n,'seq':i,'t_capture_ns':t,'t_send_ns':t+(20_000_000 if n.startswith('head') else 60_000_000),
                'rgb':rgb,'depth':depth if n.startswith('wrist') else '',
                'source':'synthetic','model':'kb4' if n.startswith('wrist') else 'pinhole','depth_kind':'sim_ideal' if n.startswith('wrist') else 'none','timing':'{}'})
    for name,rows in [('frames',frames),('joint_states',joints),('odom',odom)]:
        pd.DataFrame(rows).to_parquet(root/(name+'.parquet'),index=False)
    (root/'meta.json').write_text(json.dumps({'origin':'scripted','source':'synthetic pattern fixture','human_recording':False,'physical_robot':False},indent=2))
    return root
