"""Episode writer. Truth packets are routed only to eval_gt and never decoded by fusion."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import threading
from collections import deque
import cv2
import numpy as np
import pandas as pd
from p2.bus import Subscriber,COMMANDS
from p2.clock import now_ns
from p2.msgs import CameraFrame,JointState,Odom,Command,Status,DisplayEvidence


def config_hash():
    h=hashlib.sha256()
    for p in sorted(Path('configs').rglob('*.yaml')):h.update(str(p).encode());h.update(p.read_bytes())
    return h.hexdigest()


def code_hash():
    h=hashlib.sha256()
    for p in sorted(Path('p2').rglob('*.py')):h.update(str(p).encode());h.update(p.read_bytes())
    return h.hexdigest()


class Recorder:
    def __init__(self,path,origin='scripted',operator='script',scenario='empty',source='synthetic'):
        self.path=Path(path)
        if self.path.exists():raise FileExistsError(f'Refusing to overwrite episode: {path}')
        self.path.mkdir(parents=True);(self.path/'frames').mkdir();(self.path/'eval_gt').mkdir()
        self.tables={n:[] for n in ['actions','joint_states','odom','frames','display_evidence']};self.last_saved={};self.gt_last={}
        self.fusion=open(self.path/'fusion_meta.jsonl','w');self.truth=open(self.path/'eval_gt/poses.jsonl','w')
        self.camera_poses=open(self.path/'camera_poses.jsonl','w')
        calib=self.path/'calibration';calib.mkdir()
        for n in ['cameras','robot','scene','fusion','ui']:shutil.copy2(f'configs/{n}.yaml',calib/f'{n}.yaml')
        shutil.copytree('assets/robot',calib/'robot')
        if Path(scenario).is_file():shutil.copy2(scenario,calib/'scenario.yaml')
        import yaml
        self.meta={'source':source,'origin':origin,'operator':operator,'scenario':scenario,'scene':yaml.safe_load(Path('configs/scene.yaml').read_text())['label'],'config_hash':config_hash(),'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'t_start_ns':now_ns(),'recorded_max_hz':15,'rgb_encoding':'JPEG q90','depth_encoding':'compressed float16 npz'}
        self.meta['code_hash']=code_hash()
        if origin=='teleop':
            from p2.io.frozen_build import check
            freeze=check()
            if freeze:self.meta['frozen_build_hash']=freeze['build_hash']
        if source=='real':
            for file in ['data/realcam/video_validation/validation.json','data/realcam/phone_calibration.json','human_inputs/02_measurements.yaml']:
                shutil.copy2(file,calib/Path(file).name)
        self.end=False

    def consume(self,topic,msg,received):
        if isinstance(msg,DisplayEvidence):
            directory=self.path/'display_evidence';directory.mkdir(exist_ok=True)
            extra={}
            if msg.live_depth_points is not None:
                extra={'live_depth_points':msg.live_depth_points,'live_depth_capture_ns':msg.live_depth_capture_ns}
            filename=f'{msg.flush_seq:07}.npz';np.savez_compressed(directory/filename,points=msg.points,old_states=msg.old_states,coverage=msg.coverage,unknown=msg.unknown,hit_ns=msg.hit_ns,**extra)
            self.tables['display_evidence'].append({'t_ns':msg.t_ns,'flush_seq':msg.flush_seq,'file':filename});return
        if topic=='state/camera_pose':self.camera_poses.write(json.dumps({'t_ns':msg.t_ns,**msg.values})+'\n');return
        if topic.startswith('gt/'):
            if isinstance(msg,CameraFrame):
                if msg.t_capture_ns-self.gt_last.get(msg.cam_id,0)<int(1e9/15):return
                self.gt_last[msg.cam_id]=msg.t_capture_ns
                directory=self.path/'eval_gt'/msg.cam_id;directory.mkdir(exist_ok=True)
                np.savez_compressed(directory/f'{msg.seq:07}.npz',depth=msg.depth.astype(np.float16),t_capture_ns=msg.t_capture_ns)
            elif isinstance(msg,Status):self.truth.write(json.dumps({'t_ns':msg.t_ns,**msg.values})+'\n')
            return
        if topic=='fusion/meta':self.fusion.write(json.dumps(msg.values)+'\n');return
        if isinstance(msg,CameraFrame):
            # Frames remain at most the recording budget; the bus can run faster.
            if msg.t_capture_ns-self.last_saved.get(msg.cam_id,0)<int(1e9/15):return
            self.last_saved[msg.cam_id]=msg.t_capture_ns
            directory=self.path/'frames'/msg.cam_id;directory.mkdir(exist_ok=True)
            rgb_path=directory/f'{msg.seq:07}.jpg';cv2.imwrite(str(rgb_path),cv2.cvtColor(msg.rgb,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,90])
            depth_path=None
            if msg.depth is not None:
                depth_path=directory/f'{msg.seq:07}.npz';np.savez_compressed(depth_path,depth=msg.depth.astype(np.float16))
            self.tables['frames'].append(dict(cam_id=msg.cam_id,seq=msg.seq,t_capture_ns=msg.t_capture_ns,t_send_ns=msg.t_send_ns,t_recv_ns=received,source=msg.source,model=msg.model,width=msg.width,height=msg.height,depth_kind=msg.depth_kind,rgb=str(rgb_path.relative_to(self.path)),depth=str(depth_path.relative_to(self.path)) if depth_path else None,dropped=False,timing=json.dumps(msg.timing)))
        elif isinstance(msg,JointState):self.tables['joint_states'].append(dict(t_ns=msg.t_ns,names=msg.names,q=msg.q.tolist()))
        elif isinstance(msg,Odom):self.tables['odom'].append(dict(t_ns=msg.t_ns,pose=msg.pose.tolist()))
        elif isinstance(msg,Command):self.tables['actions'].append(dict(t_ns=msg.t_ns,action=msg.action,values=json.dumps(msg.values),origin=self.meta['origin']))
        elif isinstance(msg,Status) and topic=='status/sim' and msg.values.get('end'):self.end=True

    def close(self):
        self.meta['t_end_ns']=now_ns()
        frames=self.tables['frames'];self.meta['duration_s']=(max((x['t_capture_ns'] for x in frames),default=self.meta['t_start_ns'])-min((x['t_capture_ns'] for x in frames),default=self.meta['t_start_ns']))/1e9
        self.meta['frame_counts']={n:sum(x['cam_id']==n for x in frames) for n in sorted(set(x['cam_id'] for x in frames))}
        for name,rows in self.tables.items():pd.DataFrame(rows).to_parquet(self.path/f'{name}.parquet',index=False)
        self.fusion.close();self.truth.close();self.camera_poses.close();(self.path/'meta.json').write_text(json.dumps(self.meta,indent=2));return self.meta


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--seconds',type=float,default=0);p.add_argument('--origin',default='scripted');p.add_argument('--operator',default='script');p.add_argument('--scenario',default='empty');p.add_argument('--source',default='synthetic',choices=['synthetic','real']);p.add_argument('--control',action='store_true');p.add_argument('--cameras');p.add_argument('--fusion');args=p.parse_args()
    cv2.setNumThreads(1);rec=Recorder(args.output,args.origin,args.operator,args.scenario,args.source)
    for name in ['cameras','fusion']:
        if getattr(args,name):shutil.copy2(getattr(args,name),rec.path/'calibration'/(name+'.yaml'))
    metadata=deque();images={};running=True;overflows={}
    def receiver(topics,address='tcp://127.0.0.1:5600'):
        sub=Subscriber(topics,address,hwm=4096)
        try:
            while running:
                item=sub.recv(20)
                if not item:continue
                packet=(*item,now_ns())
                if isinstance(item[1],CameraFrame) or isinstance(item[1],DisplayEvidence):
                    key=item[0];queue=images.setdefault(key,deque(maxlen=4))
                    if len(queue)==queue.maxlen:overflows[key]=overflows.get(key,0)+1
                    queue.append(packet)
                else:metadata.append(packet)
        finally:sub.close()
    specs=[(['state/','action/','status/','gt/poses'],'tcp://127.0.0.1:5600'),(['camera/','video/','gt/depth'],'tcp://127.0.0.1:5600'),(['command'],COMMANDS),(['fusion/'],'tcp://127.0.0.1:5602')]
    threads=[threading.Thread(target=receiver,args=s,daemon=True) for s in specs]
    for thread in threads:thread.start()
    start=now_ns()
    try:
        while not rec.end and (not args.seconds or (now_ns()-start)/1e9<args.seconds):
            while metadata:
                packet=metadata.popleft();rec.consume(*packet)
                if args.control and isinstance(packet[1],Command) and packet[1].action=='record_stop':rec.end=True
            for key,queue in list(images.items()):
                if queue:rec.consume(*queue.popleft())
            time.sleep(.001)
    except KeyboardInterrupt:pass
    finally:
        running=False
        for thread in threads:thread.join(timeout=2)
        while metadata:rec.consume(*metadata.popleft())
        for queue in images.values():
            while queue:rec.consume(*queue.popleft())
        rec.meta['writer_overflows']=overflows
        print(json.dumps(rec.close(),indent=2))


if __name__=='__main__':main()
