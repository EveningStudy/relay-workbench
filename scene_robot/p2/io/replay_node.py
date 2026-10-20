"""State-complete wall-clock-rebased replay; never opens evaluation truth."""
import argparse, json, time
from pathlib import Path
import cv2, numpy as np
from p2.bus import Publisher
from p2.msgs import Status
from p2.io.episode import events,read_frame,state,replay_schedule
import yaml
from p2.clock import now_ns

def main():
    p=argparse.ArgumentParser();p.add_argument('episode');p.add_argument('--speed',type=float,default=1.0);p.add_argument('--seconds',type=float);p.add_argument('--cameras')
    p.add_argument('--timing',choices=['recorded_send','capture'],default='recorded_send')
    p.add_argument('--output-log',default='data/logs/replay_latest.json');a=p.parse_args()
    if a.speed<=0:raise ValueError('speed must be positive')
    root=Path(a.episode);items=events(root);pub=Publisher();time.sleep(.7);start=now_ns();base=items[0][0];counts={'joints':0,'odom':0,'frame':0};published=[]
    cameras=yaml.safe_load(Path(a.cameras).read_text())['cameras'] if a.cameras else None
    try:
        for delivery,priority,kind,row,capture in replay_schedule(items,a.timing):
            elapsed=(delivery-base)/1e9/a.speed
            if a.seconds and (capture-base)/1e9/a.speed>a.seconds:continue
            target=start+round(elapsed*1e9)
            while now_ns()<target:time.sleep(min(.005,max(0,(target-now_ns())/1e9)))
            if kind=='frame':
                frame=read_frame(root,row,cameras);frame.t_capture_ns=start+round((capture-base)/a.speed);frame.t_send_ns=now_ns();frame.source='replay'
                frame.timing={'t_render_ns':now_ns(),'replay_decode_not_render':True}
                pub.send('camera/'+frame.cam_id,frame)
                published.append({'cam_id':frame.cam_id,'seq':frame.seq,'recorded_capture_ns':capture,
                    'recorded_send_ns':int(row['t_send_ns']),'scheduled_delivery_ns':target,
                    't_capture_ns':frame.t_capture_ns,'t_send_ns':frame.t_send_ns})
            else:pub.send('state/'+kind,state(kind,row,target))
            counts[kind]+=1
        pub.send('status/sim',Status(now_ns(),{'end':True,'source':'replay'}));time.sleep(.2)
    finally:pub.close()
    result={'episode':str(root),'counts':counts,'source':'replay','state_complete':True,'speed':a.speed,'rebased_start_ns':start,
        'source_base_ns':base,'timing':a.timing,'rows':published,
        'scope':'Capture epochs rebased independently of release time. Recorded send timing preserves source delivery delay; recorder receipt/disk delay is not replayed. Host decode and scheduling add measured lateness.'}
    Path(a.output_log).write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
if __name__=='__main__':main()
