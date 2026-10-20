"""Descriptive expression proxies; global alignment, no nonlinear time warping.

F0 is log-transformed and z-normalised on jointly voiced frames. Energy uses
log RMS. Alignment maximises energy correlation within two seconds, retaining
the reported lag and coverage. Stylised robot pitch can invalidate F0 tracking.
"""
import numpy as np
import librosa
from scipy.signal import correlate, correlation_lags


def corr(a,b):
    if len(a)<5 or np.std(a)<1e-6 or np.std(b)<1e-6:return None
    return float(np.corrcoef((a-np.mean(a))/np.std(a),(b-np.mean(b))/np.std(b))[0,1])


def features(x):
    x=np.pad(np.asarray(x,np.float32),(0,max(0,640-len(x))))
    frames=librosa.util.frame(x,frame_length=640,hop_length=160)
    energy=np.sqrt(np.mean(frames**2,axis=0))
    f0=librosa.yin(x,fmin=65,fmax=500,sr=16000,frame_length=640,hop_length=160,center=False)
    voiced=energy>max(.001,float(energy.max())*.025)
    for i in range(len(f0)):
        lag=int(16000/f0[i]);f=frames[:,i]
        periodicity=np.dot(f[:-lag],f[lag:])/max(np.linalg.norm(f[:-lag])*np.linalg.norm(f[lag:]),1e-12)
        voiced[i]&=periodicity>.65
    return f0,energy,voiced


def expression(x,y):
    fx,ex,vx=features(x);fy,ey,vy=features(y)
    a=np.log(np.maximum(ex,1e-5));b=np.log(np.maximum(ey,1e-5))
    c=correlate(b-b.mean(),a-a.mean(),method='fft')
    lags=correlation_lags(len(b),len(a));valid=np.abs(lags)<=200
    lag=int(lags[valid][np.argmax(c[valid])])
    ix=max(0,-lag);iy=max(0,lag);n=min(len(a)-ix,len(b)-iy)
    joint=vx[ix:ix+n]&vy[iy:iy+n]
    return {'energy_envelope_correlation':corr(a[ix:ix+n],b[iy:iy+n]),
        'normalized_f0_correlation':corr(np.log(fx[ix:ix+n][joint]),np.log(fy[iy:iy+n][joint])),
        'alignment_lag_ms':lag*10,'aligned_frames':n,'joint_voiced_frames':int(joint.sum()),
        'joint_voiced_fraction':float(joint.mean()) if n else 0.,
        'method':'global log-RMS alignment +/-2 s, 40 ms frame/10 ms hop; YIN jointly periodic frames; no DTW'}
