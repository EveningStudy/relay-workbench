"""PTS-scheduled real RGB publisher, with image-derived pose and no inferred depth."""
import argparse,json,time
from pathlib import Path
import cv2,numpy as np
from p2.bus import Publisher
from p2.clock import now_ns
from p2.msgs import CameraFrame,Status
from p2.io.phone_pose import estimate


def prepare(video,output):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    calibration=json.loads(Path('data/realcam/video_validation/validation.json').read_text())
    k=np.array(calibration['camera_matrix']);d=np.array(calibration['distortion']);cap=cv2.VideoCapture(video);rows=[];last=-1e6;i=0
    cv2.setNumThreads(1)
    while True:
        ok,bgr=cap.read()
        if not ok:break
        pts=float(cap.get(cv2.CAP_PROP_POS_MSEC))/1000
        if pts-last<.099:continue
        last=pts;i+=1;im=cv2.resize(bgr,(1280,720));pose,reason=estimate(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY),k,d)
        path=out/f'{i:05}.jpg';cv2.imwrite(str(path),im,[cv2.IMWRITE_JPEG_QUALITY,90])
        if pose:pose.pop('corners')
        rows.append({'seq':i,'pts_s':pts,'rgb':path.name,'pose':pose,'pose_reason':reason,'source':'real'})
        if i%20==0:print('prepared',i,flush=True)
    cap.release();result={'video':video,'source':'real','calibration':calibration,'frames':rows,'note':'PTS from OpenCV FFmpeg decode; rebased to wall-clock epoch during replay. Capture-to-receive measures replay scheduling only, not phone hardware latency.'}
    (out/'manifest.json').write_text(json.dumps(result,indent=2));print({'prepared':len(rows),'posed':sum(r['pose'] is not None for r in rows)})


def main():
    p=argparse.ArgumentParser();p.add_argument('--video');p.add_argument('--camera',type=int,default=0);p.add_argument('--cam-id',default='real_phone');p.add_argument('--seconds',type=float,default=0);p.add_argument('--prepare');p.add_argument('--prepared',default='data/realcam/phone_prepared');p.add_argument('--reconnect',action='store_true')
    p.add_argument('--backend',choices=['MSMF','DSHOW'],default='MSMF');p.add_argument('--device-json');p.add_argument('--output');a=p.parse_args()
    if a.prepare:prepare(a.video,a.prepare);return
    pub=Publisher();time.sleep(.7);start=now_ns();rows=[];cv2.setNumThreads(1)
    try:
        if a.video:
            root=Path(a.prepared);manifest=json.loads((root/'manifest.json').read_text());k=np.array(manifest['calibration']['camera_matrix']);d=np.array(manifest['calibration']['distortion'])
            for r in manifest['frames']:
                if a.seconds and r['pts_s']>a.seconds:break
                target=start+round(r['pts_s']*1e9)
                while now_ns()<target:time.sleep(min(.01,max(0,(target-now_ns())/1e9)))
                image=cv2.cvtColor(cv2.imread(str(root/r['rgb'])),cv2.COLOR_BGR2RGB);image=cv2.undistort(image,k,d)
                pub.send('state/camera_pose',Status(target,{'cam_id':a.cam_id,'seq':r['seq'],'pose':r['pose'],'reason':r['pose_reason'],'camera_matrix':k.tolist(),'source':'real'}))
                sent=now_ns();pub.send('camera/'+a.cam_id,CameraFrame(a.cam_id,r['seq'],target,sent,'real','pinhole',1280,720,image,None,'none'))
                rows.append({'seq':r['seq'],'pts_s':r['pts_s'],'t_capture_ns':target,'t_send_ns':sent,'posed':r['pose'] is not None})
        else:
            from p2.io.live_capture import cameras,frames
            if a.device_json:
                selected=json.loads(Path(a.device_json).read_text())
            else:
                choices=[r for r in cameras(probe=False) if r['backend']==a.backend and r['index']==a.camera]
                if not choices:raise RuntimeError('Camera absent. Run python -m p2.io.live_test --list')
                selected=choices[0]
            stream=frames(selected,a.reconnect,a.seconds,log=lambda event:print(json.dumps(event),flush=True))
            try:
                for t,bgr,device,pid in stream:
                    rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB);seq=len(rows)+1
                    pub.send('camera/'+a.cam_id,CameraFrame(a.cam_id,seq,t,now_ns(),'real','pinhole',rgb.shape[1],rgb.shape[0],rgb,None,'none'))
                    rows.append({'seq':seq,'t_capture_ns':t,'device':device,'capture_pid':pid})
            finally:stream.close()
            if not rows:raise RuntimeError('Real camera produced no frames')
    finally:pub.close()
    result={'source':'real','frames':len(rows),'posed':sum(r.get('posed',False) for r in rows),'rows':rows,'hardware_latency_measured':False}
    out=Path(a.output or ('data/logs/m11_realcam_publish.json' if a.video else f'data/logs/live_publish_{start}.json'))
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2));print({k:v for k,v in result.items() if k!='rows'})


if __name__=='__main__':main()
