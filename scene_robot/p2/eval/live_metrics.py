"""Score the observation-only evidence actually sent in a browser geometry batch."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yaml
from p2.eval.geometry import Geometry
from p2.fusion.voxel_map import VoxelMap
from p2.msgs import CameraFrame


def run(folder):
    folder=Path(folder);ep=folder/'episode';cfg=yaml.safe_load((ep/'calibration/fusion.yaml').read_text());m=VoxelMap(cfg);g=Geometry(ep,m)
    rendered=Geometry(ep,m);rendered_scores=[]
    cameras=yaml.safe_load((ep/'calibration/cameras.yaml').read_text())['cameras'];browser=json.loads((folder/'browser.json').read_text());seen={}
    for s in browser['samples']:seen.setdefault(s['flush_seq'],s['t_dom_ns'])
    evidence=pd.read_parquet(ep/'display_evidence.parquet');events=[]
    for r in evidence.to_dict('records'):
        if r['flush_seq'] in seen:events.append((seen[r['flush_seq']],1,r))
    for cam in cameras:
        for path in (ep/'eval_gt'/cam).glob('*.npz'):
            with np.load(path) as data:t=int(data['t_capture_ns'])
            events.append((t,0,{'cam':cam,'path':path}))
    events.sort(key=lambda r:(r[0],r[1]));scores=[];next_score=0;next_full=0
    # Full scores every 200 ms; these are sampled response times (upper bounds).
    for t,kind,row in events:
        if kind==0:
            depth=np.load(row['path'])['depth'].astype(np.float32);h,w=depth.shape
            frame=CameraFrame(row['cam'],int(row['path'].stem),t,t,'evaluation_only',cameras[row['cam']]['model'],w,h,np.zeros((h,w,3),np.uint8),depth,'evaluation_only')
            g.observe(frame,cameras[row['cam']])
            rendered.observe(frame,cameras[row['cam']])
        elif t>=next_score:
            displayed=dict(np.load(ep/'display_evidence'/row['file']));full=t>=next_full;s=g.evaluate(t,displayed,full=full);s['flush_seq']=int(row['flush_seq']);scores.append(s);next_score=t+200_000_000
            if full:next_full=t+2_000_000_000
            if 'live_depth_points' in displayed:
                pixels={**displayed,'points':displayed['live_depth_points'],'hit_ns':displayed['live_depth_capture_ns']}
                extra=rendered.evaluate(t,pixels,full=full);extra['flush_seq']=int(row['flush_seq']);rendered_scores.append(extra)
    changes=[]
    for c in g.changes:
        result={**c}
        for key in ['live','suppressed']:
            result[key+'_after_visible_ms']=(c[key+'_ns']-c['first_visible_ns'])/1e6 if c[key+'_ns'] and c['first_visible_ns'] else None
        result['suppression_after_adequate_ms']=(c['suppressed_ns']-c['adequate_ns'])/1e6 if c['suppressed_ns'] and c['adequate_ns'] else None
        result['presence_after_visible_ms']=(c['presence_ns']-c['first_visible_ns'])/1e6 if c.get('presence_ns') and c['first_visible_ns'] else None
        result['status']='not visible in evaluation samples' if not c['first_visible_ns'] else ('response observed' if c['live_ns'] or c['suppressed_ns'] else 'right-censored; response not reached')
        changes.append(result)
    result={'metric_revision':3,'presence_rule':'At least 3 displayed occupied voxels above the support plane margin, each with >=3 integrated hits, within the unchanged 2cm surface tolerance, and post-visibility last hits. This measures partial presence, not 25% whole-object completeness; original LIVE and suppression metrics retained alongside.', 'episode':str(ep),'changes':changes,'scores':scores,'display_evidence_batches':len(evidence),'matched_browser_batches':len(seen),
        'scope':'Truth used only here. First usable visibility from GT depth/poses, sampled at <=5 Hz; actual geometry snapshots matched to browser DOM flush_seq. Response scoring at >=200ms intervals gives sampled upper bounds, not exact first GPU-presented frame. Adequate = >=3 usable observations plus >=80% obsolete prior samples observed free; for additions without obsolete prior, >=25% actor surface visibility. LIVE >=25% current actor sample support within 2cm with post-visibility hits; suppression >=80% obsolete prior samples. Obsolete excludes support still on any current GT surface. Unknown labels scored at the actual displayed coverage grid against recent pixel visibility, not random surface sample cells. Absent/unobserved is censored, not zero delay.'}
    if rendered_scores:
        result['recent_depth_display']={'scores':rendered_scores,'changes':rendered.changes,
            'scope':'Additional actual recent-pixel geometry audit. Original voxel-state gate and historical scoring rules above are unchanged; neither result substitutes for the other.'}
    (folder/'evaluation.json').write_text(json.dumps(result,indent=2));return result
