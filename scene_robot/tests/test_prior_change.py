"""Support surface and occlusion regressions for map-driven object removal."""
from types import SimpleNamespace
import numpy as np
import torch
from p2.fusion.voxel_map import VoxelMap
from p2.fusion.splat_mask import SplatMask


def fixture():
    x,y=np.meshgrid(np.arange(.1,.9,.02),np.arange(.1,.9,.02))
    plane=np.c_[x.ravel(),y.ravel(),np.full(x.size,.9)]
    x,y,z=np.meshgrid([.31,.33,.35],[.41,.43,.45],[.95,.97,.99])
    obj=np.c_[x.ravel(),y.ravel(),z.ravel()];points=np.r_[plane,obj]
    cfg=dict(device='cpu',resolution_m=.02,workspace_min=[0,0,0],workspace_max=[1,1,1.2],
        prior_cluster_mask=True,support_margin_m=.025,cluster_free_fraction=.8,
        removed_threshold=-2,live_seconds=2,live_min_hits=3,hit_logodds=.85,free_logodds=-.55,
        max_range_m=2,ray_step_m=.01,free_margin_m=.015)
    m=VoxelMap(cfg);view=SimpleNamespace(splats=SimpleNamespace(centers=points,rgb=np.ones_like(points)),
        tiles={0:np.arange(len(points))},update=lambda *args:None)
    return m,SplatMask(view,m),len(plane)


def test_occluded_cluster_stays_unverified():
    m,mask,n=fixture();mask.update(3_000_000_000)
    assert (mask.states[n:]==0).all()
    # Free evidence on the desk below an unseen object cannot clear the object.
    idx=mask.index[:n];m.logodds[idx]=-5;m.last_seen[idx]=1;m.free_count[idx]=10
    mask.update(4_000_000_000);assert (mask.states[n:]==0).all()


def test_removed_cluster_next_to_support_and_current_surface_kept():
    m,mask,n=fixture();idx=mask.index[n:];plane=mask.index[:n]
    m.logodds[plane]=4;m.last_hit[plane]=1_000_000_000
    m.logodds[idx]=-3;m.last_seen[idx]=1_000_000_000;m.free_count[idx]=8
    mask.update(1_000_000_000);assert (mask.states[n:]==2).all()
    # New consistent evidence can restore part of a previously cleared component.
    keep=idx[0];m.logodds[keep]=3;m.last_hit[keep]=2_000_000_000
    mask.update(2_000_000_000);assert (mask.states[n:][(idx==keep).numpy()]==1).all()


def test_repeated_hits_define_live_and_ray_stops_at_occluder():
    m,mask,n=fixture();origin=[.33,.43,1.15];end=np.array([[.33,.43,.99]])
    for t in [1,2]:m.integrate(origin,end,[[255,0,0]],t,weight=1)
    assert len(m.points(2)[0])==0
    m.integrate(origin,end,[[255,0,0]],3,weight=1)
    assert len(m.points(3)[0])==1
    behind,valid=m.index(torch.tensor([[.33,.43,.95]]))
    assert int(m.free_count[behind])==0


def test_cluster_votes_do_not_clear_another_unseen_component():
    m,mask,n=fixture();view=mask.view
    first=view.splats.centers[n:];view.splats.centers=np.r_[view.splats.centers,first+[.3,0,0]]
    view.splats.rgb=np.ones_like(view.splats.centers);view.tiles={0:np.arange(len(view.splats.centers))}
    mask=SplatMask(view,m);assert len(mask.cluster_indices)==2
    first_idx=mask.cluster_indices[0];m.logodds[first_idx]=-3;m.free_count[first_idx]=8;m.last_seen[first_idx]=1
    mask.update(1_000_000_000)
    assert (mask.states[mask.clusters.labels==1]==2).all()
    assert (mask.states[mask.clusters.labels==2]==0).all()


def test_spatial_consistency_preserves_small_patch_and_rejects_isolated_noise():
    m,mask,n=fixture();m.cfg['live_min_neighbors']=2
    points=np.array([[.31,.41,.95],[.33,.41,.95],[.31,.43,.95],[.71,.71,1.05]])
    idx,valid=m.index(torch.as_tensor(points));m.logodds[idx]=3;m.hit_count[idx]=3;m.last_hit[idx]=1
    shown=m.points(1)[0]
    assert len(shown)==3
    assert (shown[:,0]<.4).all()
