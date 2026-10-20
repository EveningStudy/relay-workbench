"""Validate real video and fit a separate video-specific camera calibration."""
import argparse,json
from pathlib import Path
import cv2,numpy as np
from p2.io.calibrate import detect,read_square_size
from p2.io.phone_pose import estimate


def main():
    p=argparse.ArgumentParser();p.add_argument('--video',default='human_inputs/05_phone_video/IMG_7361.MOV');a=p.parse_args()
    cv2.setNumThreads(1);out=Path('data/realcam/video_validation');out.mkdir(parents=True,exist_ok=True)
    cap=cv2.VideoCapture(a.video);fps=cap.get(cv2.CAP_PROP_FPS);count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));rows=[];images=[];cs=[]
    step=max(1,round(fps*.8));size=None
    for i in range(count):
        ok,im=cap.read()
        if not ok:break
        if i%step:continue
        pts=cap.get(cv2.CAP_PROP_POS_MSEC);im=cv2.resize(im,(1280,720));size=im.shape[1::-1]
        c,reason=detect(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY));row={'frame':i,'pts_ms':pts,'detected':c is not None,'reason':reason}
        rows.append(row);images.append(im);cs.append(c)
        print(i,reason or 'corners accepted',flush=True)
    cap.release();idx=[i for i,c in enumerate(cs) if c is not None];train=idx[::2];held=idx[1::2]
    result={'source':'real','input':a.video,'fps':fps,'frames':count,'duration_s':count/fps,'sampled':len(rows),'corner_accepted':len(idx),'size':size,'rows':rows}
    if len(train)<6:result['status']='unusable_for_video_calibration'
    else:
        square=read_square_size('human_inputs/04_phone_calibration');obj=np.zeros((70,3),np.float32);obj[:,:2]=np.mgrid[:10,:7].T.reshape(-1,2)*square
        flags=cv2.CALIB_ZERO_TANGENT_DIST|cv2.CALIB_FIX_K3
        ret,k,d,_,_=cv2.calibrateCamera([obj]*len(train),[cs[i] for i in train],size,None,None,flags=flags)
        result.update(status='video_self_calibration',rms_px=ret,camera_matrix=k.tolist(),distortion=d.ravel().tolist(),train=len(train),heldout=len(held),note='Video camera model fitted separately because portrait stills and stabilized landscape video have different crop. Held-out poses test board reprojection, not independent world accuracy.')
        for i in idx:
            pose,reason=estimate(cv2.cvtColor(images[i],cv2.COLOR_BGR2GRAY),k,d)
            rows[i].update(pose=pose,pose_rejection=reason,partition='train' if i in train else 'heldout')
            if pose:
                cv2.drawChessboardCorners(images[i],(10,7),np.array(pose['corners'],np.float32).reshape(-1,1,2),True)
                cv2.imwrite(str(out/f'overlay_{i:03}.jpg'),images[i],[cv2.IMWRITE_JPEG_QUALITY,90])
        valid=[r['pose']['rms_px'] for r in rows if r.get('pose') and r['partition']=='heldout']
        result['heldout_pose_rms_px']={'n':len(valid),'median':float(np.median(valid)) if valid else None,'p95':float(np.percentile(valid,95)) if valid else None}
    (out/'validation.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))


if __name__=='__main__':main()
