"""Score all matched recorded stereo pairs with available evaluation depth."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yaml
from p2.io.episode import read_frame
from p2.fusion.stereo import Stereo
from p2.eval.perf import stats


def run(condition_folder):
    folder=Path(condition_folder);cfg=yaml.safe_load((folder/'config.yaml').read_text());condition=cfg.get('condition',{});root=Path(cfg['episode']);tab=pd.read_parquet(root/'frames.parquet')
    cameras=yaml.safe_load((root/'calibration/cameras.yaml').read_text())['cameras'];c=cameras['head_left'];fx=c['width']/(2*np.tan(np.deg2rad(c['horizontal_fov_deg'])/2));matcher=Stereo(fx)
    left={int(r['seq']):r for r in tab[tab.cam_id=='head_left'].to_dict('records')};right={int(r['seq']):r for r in tab[tab.cam_id=='head_right'].to_dict('records')};values=[];pairs=[];rejected=0
    if condition.get('head_depth')!='sim_ideal':
        for seq in sorted(left.keys()&right.keys()):
            path=root/'eval_gt/head_left'/f'{seq:07}.npz'
            if not path.exists():continue
            a=read_frame(root,left[seq]);b=read_frame(root,right[seq]);offset=(a.t_capture_ns-b.t_capture_ns)/1e6-condition.get('stereo_offset_ms',0)
            depth,confidence,info=matcher.compute(a.rgb,b.rgb,offset)
            if depth is None:rejected+=1;continue
            gt=np.load(path)['depth'].astype(np.float32);valid=(depth>.05)&(gt>.05)&(gt<3.5);errors=np.abs(depth[valid]-gt[valid])[::20];values.extend(errors.tolist());pairs.append({'seq':seq,'pixels_sampled':len(errors),'offset_ms':offset})
    result={'sgbm_depth_error_m':stats(values),'pairs':pairs,'gated_pairs':rejected,'method':'All recorded matched seq with evaluation depth; every 20th valid depth pixel. Ideal head ablation does not run SGBM.'}
    (folder/'stereo_depth.json').write_text(json.dumps(result,indent=2));return result
