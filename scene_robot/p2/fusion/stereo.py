"""Rectified half-resolution SGBM with texture/LR confidence and timing gate."""
import cv2
import numpy as np


def sync_weight(delta_ms):
    delta_ms=abs(delta_ms)
    if delta_ms<=3:return 1.
    if delta_ms>15:return 0.
    return (15-delta_ms)/12


class Stereo:
    def __init__(self,fx,baseline=.06):
        cv2.setNumThreads(2)
        self.fx=fx;self.baseline=baseline
        self.matcher=cv2.StereoSGBM.create(minDisparity=0,numDisparities=64,blockSize=5,P1=8*25,P2=32*25,disp12MaxDiff=1,uniquenessRatio=10,speckleWindowSize=30,speckleRange=2,mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY)

    def compute(self,left,right,delta_ms):
        sync=sync_weight(delta_ms)
        if sync==0:return None,None,{'sync_weight':0,'reason':'stereo offset exceeds gate'}
        h,w=left.shape[:2];a=cv2.cvtColor(left,cv2.COLOR_RGB2GRAY);b=cv2.cvtColor(right,cv2.COLOR_RGB2GRAY)
        dl=self.matcher.compute(a,b).astype(np.float32)/16
        dr=self.matcher.compute(np.fliplr(b),np.fliplr(a)).astype(np.float32)/16;dr=np.fliplr(dr)
        yy,xx=np.mgrid[:h,:w];xr=np.rint(xx-dl).astype(int);inside=(xr>=0)&(xr<w)
        consistency=np.abs(dl-dr[yy,np.clip(xr,0,w-1)])
        af=a.astype(np.float32);texture=np.sqrt(np.maximum(0,cv2.blur(af*af,(5,5))-cv2.blur(af,(5,5))**2))
        confidence=np.clip(texture/20,0,1)*np.exp(-consistency/1.5)*sync
        valid=inside&(dl>2)&(consistency<.75)&(texture>8)
        depth=np.where(valid,self.fx*self.baseline/np.maximum(dl,.01),0).astype(np.float32);confidence[~valid]=0
        return cv2.resize(depth,(w,h),interpolation=cv2.INTER_NEAREST),cv2.resize(confidence,(w,h),interpolation=cv2.INTER_NEAREST),{'sync_weight':sync,'reason':'sgbm','valid_fraction':float(valid.mean())}
