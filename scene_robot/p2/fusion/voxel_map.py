"""Dense CUDA occupancy evidence. Prior and current evidence are separate arrays."""
import numpy as np
import torch


class VoxelMap:
    def __init__(self,cfg):
        torch.set_num_threads(4)
        self.cfg=cfg;self.device=cfg['device'];self.res=cfg['resolution_m']
        self.minimum=torch.tensor(cfg['workspace_min'],device=self.device,dtype=torch.float32)
        self.shape=np.ceil((np.array(cfg['workspace_max'])-cfg['workspace_min'])/self.res).astype(int)
        self.shape_t=torch.tensor(self.shape,device=self.device);self.n=int(np.prod(self.shape))
        self.logodds=torch.zeros(self.n,device=self.device);self.last_hit=torch.zeros(self.n,device=self.device,dtype=torch.int64);self.last_seen=self.last_hit.clone()
        self.color=torch.zeros((self.n,3),device=self.device);self.source=torch.zeros(self.n,device=self.device,dtype=torch.int64)
        self.prior=torch.zeros(self.n,device=self.device,dtype=torch.bool)
        self.hit_count=torch.zeros(self.n,device=self.device,dtype=torch.int32)
        self.free_count=torch.zeros_like(self.hit_count)
        self.last_free=self.last_hit.clone()
        from itertools import product
        self.neighbor_offsets=torch.tensor([p for p in product([-1,0,1],repeat=3) if p!=(0,0,0)],device=self.device)

    def index(self,points):
        xyz=torch.floor((points-self.minimum)/self.res).long()
        valid=((xyz>=0)&(xyz<self.shape_t)).all(-1)
        idx=(xyz[...,0]*int(self.shape[1])+xyz[...,1])*int(self.shape[2])+xyz[...,2]
        return idx,valid

    def set_prior(self,points):
        idx,valid=self.index(torch.as_tensor(points,device=self.device));self.prior[idx[valid]]=True

    def integrate(self,origin,endpoints,colors,t,weight=1.,source=1,ray_weights=None):
        end=torch.tensor(np.asarray(endpoints),device=self.device,dtype=torch.float32);origin=torch.tensor(np.asarray(origin),device=self.device,dtype=torch.float32)
        col=torch.as_tensor(colors,device=self.device,dtype=torch.float32)
        rw=torch.ones(len(end),device=self.device) if ray_weights is None else torch.as_tensor(ray_weights,device=self.device,dtype=torch.float32)
        if not len(end):return {'hits':0,'free':0}
        vector=end-origin;distance=torch.linalg.norm(vector,dim=-1);unit=vector/distance[:,None].clamp_min(1e-6)
        # Each ray ends at its first surface; there is no update behind that hit.
        steps=torch.arange(0,self.cfg['max_range_m'],self.cfg['ray_step_m'],device=self.device)
        free_points=origin+unit[:,None,:]*steps[None,:,None]
        idx,valid=self.index(free_points)
        valid&=steps[None,:]<(distance[:,None]-self.cfg['free_margin_m'])
        free_idx,finv=torch.unique(idx[valid],return_inverse=True)
        free_weights=torch.zeros(len(free_idx),device=self.device)
        free_weights.scatter_reduce_(0,finv,rw[:,None].expand_as(idx)[valid],reduce='amax',include_self=True)
        self.logodds[free_idx]+=self.cfg['free_logodds']*weight*free_weights;self.last_seen[free_idx]=t
        self.free_count[free_idx]+=1;self.last_free[free_idx]=t
        hit_idx,hvalid=self.index(end);hit_idx=hit_idx[hvalid];col=col[hvalid]
        hit_idx,inv=torch.unique(hit_idx,return_inverse=True)
        if len(hit_idx):
            sums=torch.zeros((len(hit_idx),3),device=self.device);count=torch.zeros(len(hit_idx),device=self.device)
            hit_weights=torch.zeros(len(hit_idx),device=self.device);hit_weights.scatter_reduce_(0,inv,rw[hvalid],reduce='amax',include_self=True)
            sums.index_add_(0,inv,col);count.index_add_(0,inv,torch.ones(len(inv),device=self.device))
            self.color[hit_idx]=torch.where((self.last_hit[hit_idx]==0)[:,None],sums/count[:,None],.7*self.color[hit_idx]+.3*sums/count[:,None])
            self.logodds[hit_idx]+=self.cfg['hit_logodds']*weight*hit_weights;self.last_hit[hit_idx]=t;self.last_seen[hit_idx]=t;self.source[hit_idx]|=source
            self.hit_count[hit_idx]+=1
        self.logodds.clamp_(-5,5)
        return {'hits':len(hit_idx),'free':len(free_idx)}

    def points(self,t,all_states=False):
        occupied=(self.logodds>0.5)&(self.hit_count>=self.cfg.get('live_min_hits',1));idx=torch.nonzero(occupied).flatten()
        z=idx%int(self.shape[2]);y=(idx//int(self.shape[2]))%int(self.shape[1]);x=idx//int(self.shape[2]*self.shape[1])
        xyz=torch.stack([x,y,z],-1)
        if self.cfg.get('live_min_neighbors',0) and len(idx):
            neighbors=xyz[:,None,:]+self.neighbor_offsets[None,:,:]
            valid=((neighbors>=0)&(neighbors<self.shape_t)).all(-1)
            ni=((neighbors[:,:,0]*int(self.shape[1])+neighbors[:,:,1])*int(self.shape[2])+neighbors[:,:,2]).clamp(0,self.n-1)
            keep=(occupied[ni]&valid).sum(1)>=self.cfg['live_min_neighbors']
            idx=idx[keep];xyz=xyz[keep]
        pos=self.minimum+(xyz.float()+.5)*self.res
        age=(t-self.last_hit[idx]).float()/1e9
        return pos.cpu().numpy(),self.color[idx].cpu().numpy().astype(np.uint8),age.cpu().numpy(),self.source[idx].cpu().numpy()

    def save(self,path):
        np.savez_compressed(path,logodds=self.logodds.cpu().numpy(),last_hit=self.last_hit.cpu().numpy(),last_seen=self.last_seen.cpu().numpy(),color=self.color.cpu().numpy().astype(np.uint8),source=self.source.cpu().numpy(),prior=self.prior.cpu().numpy(),hit_count=self.hit_count.cpu().numpy(),free_count=self.free_count.cpu().numpy(),last_free=self.last_free.cpu().numpy(),shape=self.shape,res=self.res,minimum=self.minimum.cpu().numpy())
