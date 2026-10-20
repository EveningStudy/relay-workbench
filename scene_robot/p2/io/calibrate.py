"""Checkerboard calibration with conservative glare/corner quality rejection."""
import argparse, json, re
from pathlib import Path
import cv2, numpy as np

PATTERN=(10, 7)  # 11 x 8 squares on checkerboard_iPadAir4_2360x1640.png

def read_square_size(folder, override=None):
    if override is not None:
        if not np.isfinite(override) or override<=0:raise ValueError('Square size must be positive metres')
        return float(override)
    board=Path(folder)/'board.txt'
    if board.exists():
        m=re.search(r'[-+]?\d+(?:\.\d+)?', board.read_text())
        if m:
            value=float(m.group())
            units=board.read_text().lower()
            value=value/1000 if 'mm' in units else value/100 if 'cm' in units else value
            if value<=0 or value>.2:raise ValueError('Square size is not plausible; specify measured metres/mm/cm')
            return value
    raise ValueError(f'Measured square size is required in {board}; no nominal/A4 fallback')

def detect(gray):
    """Return corners and a rejection reason; glare is handled conservatively."""
    scale=min(1.,1600/max(gray.shape));small=cv2.resize(gray,None,fx=scale,fy=scale) if scale<1 else gray
    flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY
    ok,c=cv2.findChessboardCornersSB(small, PATTERN, flags=flags)
    if not ok:
        ok,c=cv2.findChessboardCorners(small, PATTERN, flags=cv2.CALIB_CB_ADAPTIVE_THRESH|cv2.CALIB_CB_NORMALIZE_IMAGE)
    if not ok or c is None or len(c)!=PATTERN[0]*PATTERN[1]:
        return None,'corners_not_detected'
    c=c/scale
    c=cv2.cornerSubPix(gray,c,(5,5),(-1,-1),(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_MAX_ITER,40,.01))
    xy=c.reshape(-1,2)
    # A board with severe glare often produces a geometrically inconsistent subset
    # even when the detector returns success. Reject those frames rather than
    # letting a bad view bias calibration.
    model=np.c_[np.mgrid[:PATTERN[0],:PATTERN[1]].T.reshape(-1,2),np.zeros(len(xy))][:,:2].astype(np.float32)
    H,_=cv2.findHomography(model,xy,0)
    if H is None:return None,'homography_failed'
    pred=cv2.perspectiveTransform(model[None],H)[0]
    rms=float(np.sqrt(np.mean(np.sum((pred-xy)**2,axis=1))))
    if not np.isfinite(rms) or rms*scale>2.5:return None,f'corner_rms_normalized_px>{rms*scale:.2f}'
    # Check the centres of the dark squares. A specular highlight that clips a
    # dark square is glare; ordinary white squares are intentionally bright and
    # must not be mistaken for glare.
    centers=np.array([[x-.5,y-.5] for y in range(8) for x in range(11)],np.float32)
    samples=cv2.perspectiveTransform(centers[None],H)[0]
    dark=[]
    for parity in (0,1):
        vals=[]
        for i,(x,y) in enumerate([(x,y) for y in range(8) for x in range(11)]):
            if (x+y)%2==parity:
                u,v=np.round(samples[i]).astype(int);patch=gray[max(0,v-4):v+5,max(0,u-4):u+5]
                if patch.size:vals.append(float(np.median(patch)))
        dark.append(vals)
    dark_vals=min(dark,key=lambda values:np.median(values) if values else 255)
    if len(dark_vals)<20 or np.median(dark_vals)>180 or sum(v>240 for v in dark_vals)>=2:
        return None,'glare_clipped_dark_cells'
    return c.reshape(-1,1,2),None

def main():
 p=argparse.ArgumentParser();p.add_argument('path');p.add_argument('--square',type=float);p.add_argument('--output');a=p.parse_args();folder=Path(a.path);exts=('*.jpg','*.jpeg','*.png');files=sorted({f for e in exts for f in folder.glob(e) if '_preview' not in f.stem});square=read_square_size(folder,a.square);obj=np.zeros((PATTERN[0]*PATTERN[1],3),np.float32);obj[:,:2]=np.mgrid[:PATTERN[0],:PATTERN[1]].T.reshape(-1,2)*square;objpoints=[];imgpoints=[];size=None;rejected=[];accepted=[]
 manifest=folder/'decode_manifest.json';metadata={Path(r['decoded']).stem:r for r in json.loads(manifest.read_text())} if manifest.exists() else {}
 for f in files:
  if f.stem in metadata and '6.765mm' not in metadata[f.stem]['lens_model']:
   rejected.append({'file':str(f),'reason':'different_physical_lens'});continue
  im=cv2.imread(str(f));
  if im is None:rejected.append({'file':str(f),'reason':'image_unreadable'});continue
  native=im.shape[1::-1];factor=1600/max(native);im=cv2.resize(im,(round(native[0]*factor),round(native[1]*factor)));this_size=im.shape[1::-1]
  if size is not None and this_size!=size:rejected.append({'file':str(f),'reason':'incompatible_aspect_ratio'});continue
  size=this_size;c,reason=detect(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY))
  if c is None:rejected.append({'file':str(f),'reason':reason});continue
  objpoints.append(obj.copy());imgpoints.append(c);accepted.append(str(f));print(f.name,'accepted',flush=True)
 result={'source':'real','frames':len(files),'usable':len(objpoints),'rejected':rejected,'square_size_m':square,'image_size':size,'pattern_inner_corners':list(PATTERN),'glare_policy':'reject failed detection, homography RMS >2.5 px at max dimension1600, or clipped glare that brightens at least two expected dark cells'}
 if objpoints:
  ret,k,d,rv,tv=cv2.calibrateCamera(objpoints,imgpoints,size,None,None)
  errors=[float(np.sqrt(np.mean(np.sum((cv2.projectPoints(o,r,t,k,d)[0]-i)**2,axis=2)))) for o,i,r,t in zip(objpoints,imgpoints,rv,tv)]
  result.update(status='calibrated',rms_px=float(ret),camera_matrix=k.tolist(),distortion=d.reshape(-1).tolist(),per_image=[{'file':f,'rms_px':e} for f,e in zip(accepted,errors)],notes='Images normalized to common portrait resolution before fitting; video needs separate crop/lens validation.')
 else:result['status']='pending human checkerboard images'
 print(json.dumps(result,indent=2))
 if a.output:Path(a.output).write_text(json.dumps(result,indent=2))
if __name__=='__main__':main()
