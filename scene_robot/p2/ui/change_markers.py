"""Operator annotations from current evidence and the immutable prior only."""
from itertools import product
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree,Delaunay,ConvexHull


def connected(points,resolution,min_voxels=5):
    """Same 26-neighbour voxel connectivity used by prior suppression clusters."""
    if not len(points):return []
    coords=np.floor(np.asarray(points)/resolution+1e-5).astype(int)
    low=coords.min(0);grid=np.zeros(coords.max(0)-low+1,bool);grid[tuple((coords-low).T)]=True
    labels,n=ndimage.label(grid,np.ones((3,3,3)));per_point=labels[tuple((coords-low).T)]
    # Count occupied cells once, not a full point-array scan and unique sort
    # for every (often tiny) connected component. Duplicate inputs still count
    # as one cell, exactly as the original criterion.
    counts=np.bincount(labels[grid],minlength=n+1)
    return [np.flatnonzero(per_point==label) for label in np.flatnonzero(counts>=min_voxels)
            if label!=0]


class ChangeMarkers:
    def __init__(self,prior_points,prior_clusters,resolution,config):
        self.tree=cKDTree(prior_points);self.clusters=prior_clusters;self.resolution=resolution;self.cfg=config;self.previous=[]
        heights=np.asarray(prior_points)[:,2];floor=heights[(heights>=-.05)&(heights<.3)]
        self.floor_z=float(np.median(floor)) if len(floor) else 0.
        plane=self.clusters.plane_z if self.clusters else .9
        support=np.asarray(prior_points)[np.abs(heights-plane)<.02,:2]
        # Only convex-hull membership is used, not interior interpolation.
        # Triangulating thousands of near-duplicate scan samples made every
        # marker decision expensive; the hull vertices define the same region.
        self.support_hull=Delaunay(support[ConvexHull(support).vertices]) if len(support)>3 else None

    def update(self,points,live,sources,prior_states,cluster_trace,observed_points=None):
        # Read-only copies of occupied LIVE evidence. No labels or scene objects.
        ids=np.flatnonzero(live);current=np.asarray(points)[ids]
        plane=self.clusters.plane_z if self.clusters is not None else .9
        margin=self.clusters.margin if self.clusters is not None else .025
        # Isolate above-support evidence before connecting it, so tabletop cells
        # do not merge an object into a whole-desk component. The support comes
        # from the scan; no hand-authored target region or object position.
        on_table=(current[:,2]>plane+margin)
        below=(current[:,2]>self.floor_z+.25)&(current[:,2]<plane-.03)
        if self.support_hull is not None:
            # One exact hull test, only where height can admit a marker. Floor
            # and support-plane cells cannot pass either branch regardless of XY.
            relevant=on_table|below;inside=np.zeros(len(current),bool)
            inside[relevant]=self.support_hull.find_simplex(current[relevant,:2])>=0
            on_table&=inside;below&=~inside
        eligible=on_table|below
        current=current[eligible];bits=np.asarray(sources)[ids][eligible];markers=[];pending=[]
        # Ineligible floor/table points never enter a marker; avoid their costly
        # prior-neighbour queries while retaining the exact same novelty test.
        novelty=self.tree.query(current,workers=1)[0]>self.cfg['novel_distance_m'] if len(current) else np.array([],bool)
        novelty&=current[:,2]>self.floor_z+.04
        for selection in connected(current,self.resolution,self.cfg['novel_min_voxels']):
            p=current[selection];bounds=np.array([p.min(0),p.max(0)]);center=bounds.mean(0)
            # Tabletop candidates are above its scan-derived support plane;
            # floor-supported candidates (e.g. a chair) can be below it.
            if bounds[1,2]-bounds[0,2]<2*self.resolution-1e-5:continue
            # Test novelty on the connected component, retaining its near-prior
            # boundary cells. Cutting them first fragments small partial objects.
            if novelty[selection].sum()<3 or novelty[selection].mean()<self.cfg.get('novel_fraction',.35):continue
            previous=[r for r in self.previous if np.linalg.norm(r['center']-center)<.10]
            count=1+max((r['count'] for r in previous),default=0)
            pending.append({'center':center,'count':count})
            if count<self.cfg['novel_confirmations']:continue
            # Retain the full LIVE cell extent as a lower bound, then include
            # actual recent samples belonging to those cells. Never infer the
            # unobserved part of a semantic object or shrink to a decimated blob.
            observed=np.empty((0,3))
            if observed_points is not None and len(observed_points):
                cell_tree=cKDTree(p)
                distance=cell_tree.query(observed_points,p=np.inf,workers=1)[0]
                observed=np.asarray(observed_points)[distance<=self.resolution/2+1e-5]
            fitted=bounds+np.array([[-1,-1,-1],[1,1,1]])*self.resolution/2
            if len(observed):fitted=np.array([np.minimum(fitted[0],observed.min(0)),np.maximum(fitted[1],observed.max(0))])
            fitted+=np.array([[-1,-1,-1],[1,1,1]])*self.cfg.get('marker_margin_m',.008)
            markers.append({'kind':'new','label':'NEW since scan','bounds':fitted.tolist(),
                'bounds_scope':'observed LIVE surfaces only, not full object size',
                'observed_points':len(observed),'points':len(p),'sources':int(np.bitwise_or.reduce(bits[selection]))})
        self.previous=pending
        if self.clusters is not None:
            trace={r['id']:r for r in cluster_trace}
            for k,component in enumerate(self.clusters.components,1):
                states=np.asarray(prior_states)[component['ids']]
                if np.ptp(component['bounds'][:,2])<.04:continue
                if trace.get(k,{}).get('clear') and len(states) and np.mean(states==2)>=.8:
                    markers.append({'kind':'removed','label':'REMOVED since scan','bounds':component['bounds'].tolist(),
                        'prior_cluster':k,'removed_fraction':float(np.mean(states==2))})
        return markers


def box_segments(bounds,dashed=False):
    low,high=np.asarray(bounds);bits=np.array(list(product([0,1],repeat=3)));corners=np.where(bits,high,low)
    edges=[]
    for i,a in enumerate(corners):
        for j,b in enumerate(corners):
            if j<=i or np.count_nonzero(bits[i]!=bits[j])!=1:continue
            if dashed:
                for start in np.arange(0,1,.16):edges.append([a+(b-a)*start,a+(b-a)*min(1,start+.08)])
            else:edges.append([a,b])
    return np.asarray(edges,dtype=np.float32)
