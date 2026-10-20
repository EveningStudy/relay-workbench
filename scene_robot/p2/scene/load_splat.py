"""Read standard Gaussian PLY attributes and covariance, with no simulator data."""
from dataclasses import dataclass
import numpy as np
from plyfile import PlyData, PlyElement
from scipy.spatial.transform import Rotation

SH_C0=0.28209479177387814


@dataclass
class Splats:
    centers: np.ndarray
    covariance: np.ndarray
    rgb: np.ndarray
    opacity: np.ndarray


def load(path):
    v=PlyData.read(str(path))['vertex'].data
    centers=np.stack([v[n] for n in ['x','y','z']],-1)
    rgb=np.clip(.5+SH_C0*np.stack([v[f'f_dc_{i}'] for i in range(3)],-1),0,1)
    opacity=1/(1+np.exp(-np.clip(v['opacity'],-30,30)))
    scales=np.exp(np.stack([v[f'scale_{i}'] for i in range(3)],-1))
    quat=np.stack([v[f'rot_{i}'] for i in range(4)],-1)
    quat/=np.maximum(np.linalg.norm(quat,axis=-1,keepdims=True),1e-12)
    r=Rotation.from_quat(quat,scalar_first=True).as_matrix()
    cov=np.einsum('nij,nj,nkj->nik',r,scales**2,r)
    return Splats(centers.astype(np.float32),cov.astype(np.float32),rgb.astype(np.float32),opacity[:,None].astype(np.float32))


def save(path,centers,rgb,scale=.005,opacity=.9):
    names=['x','y','z','nx','ny','nz']+[f'f_dc_{i}' for i in range(3)]+['opacity']+[f'scale_{i}' for i in range(3)]+[f'rot_{i}' for i in range(4)]
    v=np.zeros(len(centers),dtype=[(n,'f4') for n in names])
    for i,n in enumerate(['x','y','z']):v[n]=centers[:,i]
    for i in range(3):v[f'f_dc_{i}']=(rgb[:,i]-.5)/SH_C0;v[f'scale_{i}']=np.log(scale)
    v['opacity']=np.log(opacity/(1-opacity));v['rot_0']=1
    PlyData([PlyElement.describe(v,'vertex')],text=False).write(str(path))
