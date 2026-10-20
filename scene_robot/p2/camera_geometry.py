"""Five pinhole faces remapped into a circular equidistant KB4 image."""
import cv2
import numpy as np
from scipy.spatial.transform import Rotation


FACE_ROTATIONS = np.stack([np.eye(3), Rotation.from_euler("y", np.pi/2).as_matrix(), Rotation.from_euler("y", -np.pi/2).as_matrix(), Rotation.from_euler("x", np.pi/2).as_matrix(), Rotation.from_euler("x", -np.pi/2).as_matrix()])


def project_kb(points, size=512, coeff=(0,0,0,0)):
    p=np.asarray(points);theta=np.arctan2(np.linalg.norm(p[...,:2],axis=-1),p[...,2])
    radius=theta.copy()
    for i,k in enumerate(coeff): radius+=k*theta**(3+2*i)
    xy=p[...,:2]/np.maximum(np.linalg.norm(p[...,:2],axis=-1,keepdims=True),1e-12)
    return xy*radius[...,None]*(size/np.pi)+(size-1)/2


def rays_kb(size=512, coeff=(0,0,0,0)):
    y,x=np.mgrid[:size,:size];u=(x-(size-1)/2)/(size/np.pi);v=(y-(size-1)/2)/(size/np.pi)
    r=np.sqrt(u*u+v*v);theta=r.copy()
    for _ in range(8):
        f=theta.copy();df=np.ones_like(theta)
        for i,k in enumerate(coeff): f+=k*theta**(3+2*i);df+=(3+2*i)*k*theta**(2+2*i)
        theta-=(f-r)/df
    scale=np.sin(theta)/np.maximum(r,1e-12)
    return np.stack([u*scale,v*scale,np.cos(theta)],-1).astype(np.float32),theta<=np.pi/2


class CubeRemap:
    def __init__(self,size=512,face_size=256,coeff=(0,0,0,0)):
        self.rays,self.valid=rays_kb(size,coeff)
        local=np.einsum('hwi,fij->fhwj',self.rays,FACE_ROTATIONS)
        self.faces=np.argmax(local[...,2],axis=0)
        self.maps=[]
        for i in range(5):
            d=local[i];z=np.maximum(d[...,2],1e-6)
            self.maps.append(((d[...,0]/z*face_size/2+(face_size-1)/2).astype(np.float32),(d[...,1]/z*face_size/2+(face_size-1)/2).astype(np.float32)))
        self.atlas_x=np.zeros(self.valid.shape,np.float32);self.atlas_y=self.atlas_x.copy()
        for i,(mx,my) in enumerate(self.maps):
            mask=self.faces==i
            self.atlas_x[mask]=np.clip(mx[mask],0,face_size-1)+i*face_size
            self.atlas_y[mask]=np.clip(my[mask],0,face_size-1)

    def apply(self,images,distances):
        rgb=cv2.remap(np.concatenate(images,axis=1),self.atlas_x,self.atlas_y,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
        depth=cv2.remap(np.concatenate(distances,axis=1),self.atlas_x,self.atlas_y,cv2.INTER_NEAREST,borderMode=cv2.BORDER_REPLICATE)
        rgb[~self.valid]=0;depth[~self.valid]=0
        return rgb,depth
