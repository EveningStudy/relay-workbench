"""Static-map support plane and connected components, without scene labels."""
import numpy as np
from scipy import ndimage


class PriorClusters:
    def __init__(self,points,resolution=.02,margin=.025):
        self.margin=margin;self.resolution=resolution
        # Gravity-aligned map: strongest horizontal height mode above the floor.
        heights=points[:,2];candidate=heights[(heights>.3)&(heights<1.3)]
        hist,edges=np.histogram(candidate,bins=np.arange(.3,1.31,.01))
        mode=(edges[hist.argmax()]+edges[hist.argmax()+1])/2
        self.plane_z=float(np.median(heights[np.abs(heights-mode)<.015]))
        self.labels=np.zeros(len(points),np.int32);self.components=[]
        ids=np.flatnonzero(heights>self.plane_z+margin)
        if not len(ids):return
        coords=np.floor(points[ids]/resolution).astype(int);low=coords.min(0);coords-=low
        grid=np.zeros(coords.max(0)+1,bool);grid[tuple(coords.T)]=True
        labels,n=ndimage.label(grid,np.ones((3,3,3)))
        per_point=labels[tuple(coords.T)]
        for label in range(1,n+1):
            selected=ids[per_point==label]
            voxels=np.unique(np.floor(points[selected]/resolution).astype(int),axis=0)
            if len(voxels)<5:continue
            k=len(self.components)+1;self.labels[selected]=k
            self.components.append({'ids':selected,'centers':(voxels+.5)*resolution,
                'bounds':np.array([points[selected].min(0),points[selected].max(0)])})

    def summary(self):
        return {'plane_z':self.plane_z,'margin_m':self.margin,'resolution_m':self.resolution,
            'components':[{'id':i+1,'gaussians':len(c['ids']),'voxels':len(c['centers']),
                'bounds':c['bounds'].tolist()} for i,c in enumerate(self.components)]}
