"""Evidence-driven per-tile masking with bounded update frequency."""
import numpy as np
import torch


class SplatMask:
    def __init__(self,view,voxel_map):
        self.view=view;self.map=voxel_map
        idx,valid=voxel_map.index(torch.tensor(view.splats.centers,device=voxel_map.device))
        self.index=idx.clamp(0,voxel_map.n-1);self.valid=valid
        self.visible=np.ones(len(idx),bool);self.last_update={};self.removed_count=0
        self.states=np.full(len(idx),-1,np.int8);self.last_style=None
        self.clusters=None;self.cluster_indices=[];self.cluster_trace=[]
        if voxel_map.cfg.get('prior_cluster_mask',False):
            from p2.fusion.prior_clusters import PriorClusters
            self.clusters=PriorClusters(view.splats.centers,voxel_map.res,voxel_map.cfg.get('support_margin_m',.025))
            for component in self.clusters.components:
                ci,cv=voxel_map.index(torch.as_tensor(component['centers'],device=voxel_map.device,dtype=torch.float32))
                self.cluster_indices.append(ci[cv])
            # Pack once. Per-component .item()/float() used to force dozens of
            # host/device synchronizations during every mask upload.
            self.component_labels=torch.as_tensor(self.clusters.labels,device=voxel_map.device,dtype=torch.long)
            self.vote_indices=torch.cat(self.cluster_indices) if self.cluster_indices else self.index[:0]
            self.vote_labels=torch.cat([torch.full_like(idx,k+1) for k,idx in enumerate(self.cluster_indices)]) if self.cluster_indices else self.index[:0]
            self.vote_sizes=torch.bincount(self.vote_labels,minlength=len(self.cluster_indices)+1).clamp_min(1)

    def update(self,t,show_verified=True,show_unverified=True,tint=True):
        m=self.map;removed=(m.logodds[self.index]<=m.cfg['removed_threshold'])&(m.last_seen[self.index]>0)&self.valid
        # A partly free boundary voxel is not enough to erase a nearby surface.
        if self.clusters is None:
            occupied=(m.logodds>.5).reshape(1,1,*map(int,m.shape)).float()
            neighborhood=torch.nn.functional.max_pool3d(occupied,3,stride=1,padding=1).flatten().bool()
            removed&=~neighborhood[self.index]
        else:
            free=(m.logodds[self.vote_indices]<=m.cfg['removed_threshold'])&(m.free_count[self.vote_indices]>=3)
            fractions=torch.bincount(self.vote_labels,weights=free.float(),minlength=len(self.vote_sizes))/self.vote_sizes
            clear=fractions>=m.cfg.get('cluster_free_fraction',.8);clear[0]=False
            current=(m.logodds[self.index]>.5)&((t-m.last_hit[self.index])<int(m.cfg['live_seconds']*1e9))
            removed=torch.where(clear[self.component_labels],~current,removed)
            supported=torch.bincount(self.component_labels,weights=current.float(),minlength=len(self.vote_sizes))
            trace=torch.stack([fractions,clear.float(),supported],dim=1).cpu().numpy()
            self.cluster_trace=[{'id':k,'free_fraction':float(r[0]),'clear':bool(r[1]),'current_support':int(r[2])} for k,r in enumerate(trace) if k]
        verified=(m.logodds[self.index]>.5)&((t-m.last_hit[self.index])<int(m.cfg['live_seconds']*1e9))&self.valid
        states=np.where(removed.cpu().numpy(),2,np.where(verified.cpu().numpy(),1,0))
        visible=(states!=2)&np.where(states==1,show_verified,show_unverified)
        changed=(states!=self.states)|(visible!=self.visible)
        style=(show_verified,show_unverified,tint)
        if style!=self.last_style:changed[:]=True;self.last_style=style
        colors=self.view.splats.rgb.copy()
        if tint:colors[states==0]=colors[states==0]*.7+np.array([.1,.06,.16])
        for key,indices in self.view.tiles.items():
            if changed[indices].any() and t-self.last_update.get(key,0)>=200_000_000:
                self.view.update(key,visible,colors);self.visible[indices]=visible[indices];self.states[indices]=states[indices];self.last_update[key]=t
        self.removed_count=int((self.states==2).sum())
        return self.removed_count
