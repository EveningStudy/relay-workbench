"""Bounded display-only depth samples, admitted by the unchanged LIVE voxel map.

No surface completion: every coordinate/colour is from an accepted depth pixel
and the same capture-time calibration/pose used by fusion. This module has no
file, transport, renderer or device access, and never writes to the map.
"""
from collections import deque
from dataclasses import dataclass
import numpy as np


@dataclass
class Samples:
    points: np.ndarray
    colors: np.ndarray
    capture_ns: np.ndarray
    sources: np.ndarray
    sequences: np.ndarray
    frame_ids: np.ndarray

    def select(self,ids):
        return Samples(*(getattr(self,key)[ids] for key in self.__dataclass_fields__))

    @classmethod
    def empty(cls):
        return cls(np.empty((0,3),np.float32),np.empty((0,3),np.uint8),
                   np.empty(0,np.int64),np.empty(0,np.int64),np.empty(0,np.int64),np.empty(0,np.int64))


def evenly_spaced(count,budget):
    """Deterministic bounded selection; never synthesizes or averages pixels."""
    return np.linspace(0,count-1,min(count,budget),dtype=np.int64) if count else np.empty(0,np.int64)


class RecentLivePoints:
    def __init__(self,config,fusion_config):
        self.cfg=config;self.res=fusion_config['resolution_m']
        self.minimum=np.asarray(fusion_config['workspace_min'],np.float32)
        self.maximum=np.asarray(fusion_config['workspace_max'],np.float32)
        # Match VoxelMap's float64 config arithmetic for dimensions; coordinate
        # indexing itself uses the same float32 minimum/points as the map.
        self.shape=np.ceil((np.asarray(fusion_config['workspace_max'])-fusion_config['workspace_min'])/self.res).astype(np.int64)
        self.max_range=fusion_config['max_range_m'];self.buffers={}
        self.shown=Samples.empty();self.last_refresh_ns=None;self.revision=0;self.telemetry_revision=-1;self.observations=[]
        self.frame_id=0
        self.live_lookup=np.zeros(int(np.prod(self.shape)),bool)
        for key in ('point_budget','points_per_frame','frames_per_camera','pixel_stride'):
            if int(config[key])<1:raise ValueError(key+' must be positive')
        if not 0<config['window_s']<=1:raise ValueError('Recent display window must be in (0, 1] seconds')
        if config['update_hz']<=0:raise ValueError('Live display update rate must be positive')

    def accept(self,frame,pose,rays,confidence,source):
        """Called only after normal fusion acceptance, including the stereo gate."""
        if frame.depth is None or frame.depth_kind not in ('sim_ideal','sgbm'):return
        stride=int(self.cfg['pixel_stride']);phase=frame.seq
        sample=(slice((phase//stride)%stride,None,stride),slice(phase%stride,None,stride))
        depth=np.asarray(frame.depth[sample],np.float32);ray=rays[sample]
        valid=np.isfinite(depth)&(depth>.05)&(depth<self.max_range)&np.isfinite(ray).all(-1)
        if frame.model=='kb4':valid&=ray[...,2]>=0
        if confidence is not None:valid&=confidence[sample]>.35
        ids=np.flatnonzero(valid)
        ids=ids[evenly_spaced(len(ids),int(self.cfg['points_per_frame']))]
        local=ray.reshape(-1,3)[ids]*depth.ravel()[ids,None]
        world=(local@pose[:3,:3].T+pose[:3,3]).astype(np.float32)
        color=frame.rgb[sample].reshape(-1,3)[ids].copy()
        keep=np.isfinite(world).all(1)&((world>=self.minimum)&(world<self.maximum)).all(1)
        world=world[keep];color=color[keep];n=len(world)
        self.frame_id+=1
        points=Samples(world,color,np.full(n,frame.t_capture_ns,np.int64),
                       np.full(n,source,np.int64),np.full(n,frame.seq,np.int64),np.full(n,self.frame_id,np.int64))
        queue=self.buffers.setdefault(frame.cam_id,deque(maxlen=int(self.cfg['frames_per_camera'])))
        # A duplicate or reordered observation must not displace a newer frame.
        if queue and frame.t_capture_ns<=queue[-1][0]:return
        queue.append((frame.t_capture_ns,points))

    def keys(self,points):
        xyz=np.floor((np.asarray(points,np.float32)-self.minimum)/self.res).astype(np.int64)
        return (xyz[:,0]*self.shape[1]+xyz[:,1])*self.shape[2]+xyz[:,2]

    def _gate(self,samples,keys,now,floor_height,show_floor):
        fresh=(samples.capture_ns<=now)&(samples.capture_ns>=now-int(self.cfg['window_s']*1e9))
        if not show_floor:fresh&=samples.points[:,2]>=floor_height
        cell=self.keys(samples.points);valid=(cell>=0)&(cell<len(self.live_lookup))
        return fresh&valid&self.live_lookup[np.clip(cell,0,len(self.live_lookup)-1)]

    def select(self,now,live_centres,floor_height,show_floor=False):
        """Refresh independently of geometry flush; revoke expired/non-LIVE every flush."""
        keys=self.keys(live_centres);cutoff=now-int(self.cfg['window_s']*1e9)
        self.live_lookup.fill(False)
        self.live_lookup[keys[(keys>=0)&(keys<len(self.live_lookup))]]=True
        for queue in self.buffers.values():
            while queue and queue[0][0]<cutoff:queue.popleft()
        due=self.last_refresh_ns is None or now-self.last_refresh_ns>=1e9/self.cfg['update_hz']
        if due:
            groups=[]
            for queue in self.buffers.values():
                if not queue:continue
                rows=[row for _,row in reversed(queue)]
                group=Samples(*(np.concatenate([getattr(row,key) for row in rows]) for key in Samples.__dataclass_fields__))
                group=group.select(self._gate(group,keys,now,floor_height,show_floor))
                if len(group.points):groups.append(group)
            # Fair per-camera cap prevents the high-rate head starving a wrist.
            budget=int(self.cfg['point_budget']);base,extra=divmod(budget,max(1,len(groups)))
            selected=[g.select(evenly_spaced(len(g.points),base+(i<extra))) for i,g in enumerate(groups)]
            self.shown=(Samples(*(np.concatenate([getattr(g,key) for g in selected]) for key in Samples.__dataclass_fields__))
                        if selected else Samples.empty())
            self.last_refresh_ns=now;self.revision+=1
        else:
            keep=self._gate(self.shown,keys,now,floor_height,show_floor)
            if not keep.all():self.shown=self.shown.select(keep);self.revision+=1
        return self.shown,due

    def telemetry(self):
        if self.telemetry_revision!=self.revision:
            self.observations=[]
            if len(self.shown.points):
                # Integer frame identities avoid sorting a structured triple for
                # every point whenever one sample is revoked between refreshes.
                _,first=np.unique(self.shown.frame_ids,return_index=True)
                for i in first:
                    self.observations.append({'source_bit':int(self.shown.sources[i]),'seq':int(self.shown.sequences[i]),
                                              't_capture_ns':int(self.shown.capture_ns[i])})
            self.telemetry_revision=self.revision
        return {'revision':self.revision,'points':len(self.shown.points),
                'buffered_points':sum(len(row.points) for q in self.buffers.values() for _,row in q),
                'observations':self.observations,'last_refresh_ns':self.last_refresh_ns}
