"""Tiled static prior rendering; future changes can only be driven by evidence masks."""
import numpy as np
from p2.scene.load_splat import load


class SplatView:
    def __init__(self,server,path='assets/scan/old_map.ply',tile_size=.25):
        self.server=server;self.splats=load(path);self.tiles={};self.handles={}
        tiles=np.floor(self.splats.centers/tile_size).astype(int)
        unique,inverse=np.unique(tiles,axis=0,return_inverse=True)
        for i,xyz in enumerate(unique):
            key=tuple(xyz);self.tiles[key]=np.flatnonzero(inverse==i);self.update(key)

    def update(self,key,visible_mask=None,colors=None):
        idx=self.tiles[key];s=self.splats;opacity=s.opacity[idx].copy()
        if visible_mask is not None:opacity[~visible_mask[idx]]=0
        if key not in self.handles:
            self.handles[key]=self.server.scene.add_gaussian_splats('/old_map/'+','.join(map(str,key)),s.centers[idx],s.covariance[idx],s.rgb[idx] if colors is None else colors[idx],opacity)
        else:
            # Pinned viser 1.1.1 GaussianSplatHandle documents eight uint32s
            # per Gaussian, last word RGBA. Preserve immutable center/covariance
            # words and submit one copied public buffer property update.
            handle=self.handles[key];buffer=handle.buffer.copy()
            rgba=buffer[:,7:8].view(np.uint8).reshape(-1,4)
            rgba[:,:3]=np.clip((s.rgb[idx] if colors is None else colors[idx])*255,0,255).astype(np.uint8)
            rgba[:,3:4]=np.clip(opacity*255,0,255).astype(np.uint8)
            handle.buffer=buffer
