"""Replay approved phone RGB and its image-derived board pose into the operator."""
from pathlib import Path
import argparse,json,sys,time
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scene_robot'))
CAMERA=ROOT/'scene_robot/assets/kitchen/phone_camera.json'
TRACK=ROOT/'scene_robot/assets/kitchen/phone_track.json'
VIDEO=ROOT/'docs/media/phone_excerpt.mp4'

def images():
    cap=cv2.VideoCapture(str(VIDEO));frames=[]
    try:
        for i in range(72):
            cap.set(cv2.CAP_PROP_POS_MSEC,i/6*1000);ok,bgr=cap.read()
            if not ok:raise RuntimeError(f'Phone excerpt frame {i} could not be decoded')
            frames.append(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB))
    finally:cap.release()
    return frames

def prepare():
    from p2.io.phone_pose import estimate
    cv2.setNumThreads(1)
    cfg=json.loads(CAMERA.read_text());k=np.asarray(cfg['camera_matrix']);d=np.asarray(cfg['distortion']);rows=[]
    for i,rgb in enumerate(images()):
        pose,reason=estimate(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY),k,d,cfg['board_world_points'])
        if pose:pose.pop('corners')
        rows.append({'seq':i+1,'t_s':i/6,'original_t_s':6+i/6,'pose':pose,'reason':reason})
    result={'fps':6,'duration_s':12,'width':960,'height':540,'source_interval_s':[6,18],
        'method':'Original checkerboard detector/PnP, recomputed from the approved silent public excerpt. Known measured board pose and historical video-fitted intrinsics; not independent world accuracy or hardware latency.',
        'invalid_policy':'No interpolation. Hide current frustum whenever pose is unavailable.',
        'valid':sum(r['pose'] is not None for r in rows),'frames':rows}
    TRACK.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'prepared':len(rows),'valid':result['valid'],'unavailable':len(rows)-result['valid']}))

def replay(loops,speed):
    from p2.bus import Publisher
    from p2.clock import now_ns
    from p2.msgs import CameraFrame,Status
    cfg=json.loads(CAMERA.read_text());track=json.loads(TRACK.read_text());k=np.asarray(cfg['camera_matrix']);d=np.asarray(cfg['distortion'])
    frames=[cv2.undistort(rgb,k,d) for rgb in images()];pub=Publisher();count=0
    try:
        time.sleep(.7)
        for _ in range(loops):
            start=now_ns()
            for row,rgb in zip(track['frames'],frames):
                target=start+round(row['t_s']/speed*1e9)
                while now_ns()<target:time.sleep(max(0,min(.005,(target-now_ns())/1e9)))
                pub.send('state/camera_pose',Status(target,{'cam_id':'real_phone','seq':row['seq'],
                    'pose':row['pose'],'reason':row['reason'],'camera_matrix':k.tolist(),'source':'real'}))
                pub.send('camera/real_phone',CameraFrame('real_phone',row['seq'],target,now_ns(),
                    'real','pinhole',960,540,rgb,None,'none'));count+=1
        print(json.dumps({'frames':count,'valid_per_loop':track['valid'],'scope':'Recorded RGB and board-derived pose only; no depth or hardware-latency result.'}))
    finally:pub.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--loops',type=int,default=1);p.add_argument('--speed',type=float,default=1);a=p.parse_args()
    if a.loops<1 or a.speed<=0:p.error('loops and speed must be positive')
    if a.prepare:prepare()
    else:replay(a.loops,a.speed)

if __name__=='__main__':main()
