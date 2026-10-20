"""Read a small RGB/state excerpt of the historical simulator recording."""
from pathlib import Path
import io,json,zipfile
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'scene_robot/assets/kitchen/camera_replay.zip'

class Replay:
    def __init__(self,path=ARCHIVE):
        self.archive=zipfile.ZipFile(path)
        self.manifest=json.loads(self.archive.read('replay.json'))
        self.streams={cam:sorted([r for r in self.manifest['frames'] if r['cam_id']==cam],key=lambda r:r['send_ns'])
                      for cam in ['head_left','head_right','wrist_left','wrist_right','external']}
        self.images={}

    def latest(self,cam,t):
        ready=[r for r in self.streams[cam] if r['send_ns']<=round(t*1e9)]
        return ready[-1] if ready else None

    def image(self,row):
        if row['rgb'] not in self.images:
            self.images[row['rgb']]=Image.open(io.BytesIO(self.archive.read(row['rgb']))).convert('RGB')
        return self.images[row['rgb']]

    def joints(self,t):
        rows=[r for r in self.manifest['joints'] if r['t_ns']<=round(t*1e9)]
        row=rows[-1] if rows else self.manifest['joints'][0]
        return dict(zip(row['names'],row['q']))

    def close(self):self.archive.close()

def main():
    import argparse,sys,time
    sys.path.insert(0,str(ROOT/'scene_robot'))
    from p2.bus import Publisher
    from p2.clock import now_ns
    from p2.msgs import CameraFrame,JointState,Odom
    p=argparse.ArgumentParser();p.add_argument('--speed',type=float,default=1);p.add_argument('--loops',type=int,default=1);a=p.parse_args()
    if a.speed<=0 or a.loops<1:p.error('speed and loops must be positive')
    replay=Replay();publisher=Publisher();counts={'frames':0,'joints':0,'odom':0}
    try:
        time.sleep(.7)
        for _ in range(a.loops):
            events=[(r['send_ns'],'frame',r) for r in replay.manifest['frames'] if r['cam_id']!='external']
            events += [(r['t_ns'],'joints',r) for r in replay.manifest['joints']]
            events += [(r['t_ns'],'odom',r) for r in replay.manifest['odom']]
            start=now_ns()
            for timestamp,kind,row in sorted(events,key=lambda e:e[0]):
                target=start+round(timestamp/a.speed)
                while now_ns()<target:time.sleep(max(0,min(.005,(target-now_ns())/1e9)))
                if kind=='frame':
                    rgb=np.asarray(replay.image(row))
                    frame=CameraFrame(row['cam_id'],row['seq'],start+round(row['capture_ns']/a.speed),now_ns(),
                        'replay',row['model'],row['width'],row['height'],rgb,None,'none')
                    publisher.send('camera/'+row['cam_id'],frame);counts['frames']+=1
                elif kind=='joints':
                    publisher.send('state/joints',JointState(target,row['names'],np.asarray(row['q'])));counts['joints']+=1
                else:
                    publisher.send('state/odom',Odom(target,np.asarray(row['pose'])));counts['odom']+=1
        print(json.dumps({'passed':True,'counts':counts,'scope':'Historical RGB/state replay; no bundled wrist depth, physical robot or timing measurement.'}))
    finally:publisher.close();replay.close()

if __name__=='__main__':main()
