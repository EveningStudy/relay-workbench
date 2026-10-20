"""Evaluation-only surfaces, visibility and map scores. Never imported by operating code."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
import torch
import trimesh
import yaml
from p2.scene.build_sim_scene import meshes
from p2.scene.load_splat import load
from p2.fusion.splat_mask import SplatMask
from p2.camera_geometry import project_kb


class EvidenceView:
    def __init__(self):
        self.splats=load('assets/scan/old_map.ply');self.tiles={0:np.arange(len(self.splats.centers))}
    def update(self,*args):pass


class Geometry:
    def __init__(self,episode,voxel_map):
        root=Path(episode);self.cfg=yaml.safe_load((root/'calibration/scene.yaml').read_text());self.parts={n:m for n,m,c in meshes(self.cfg)}
        from p2.scene.chair import chair_boxes
        chair=[]
        for part,center,size in chair_boxes(self.cfg):
            mesh=trimesh.creation.box(size);mesh.apply_translation(center);chair.append(mesh)
        self.parts['chair']=trimesh.util.concatenate(chair);self.parts['new_mug']=self.parts['mug'].copy()
        self.truth=[json.loads(s) for s in (root/'eval_gt/poses.jsonl').read_text().splitlines()];self.times=np.array([r['t_ns'] for r in self.truth],np.int64)
        self.gt_depth={int(p.stem):p for p in (root/'eval_gt/head_left').glob('*.npz')}
        self.map=voxel_map;self.view=EvidenceView();self.mask=SplatMask(self.view,voxel_map)
        self.original={n:m.copy() for n,m in self.parts.items() if n not in ('floor','chair','new_mug')}
        # Fixed sample points avoid random Monte Carlo changes between conditions.
        self.samples={n:trimesh.sample.sample_surface(m,max(300,int(m.area*1200)),seed=7)[0] for n,m in self.parts.items()}
        self.initial=self.truth[0];self.last_observe={}
        d=self.cfg['desk'];gx,gy=np.meshgrid(np.arange(0,d['width_x'],.08),np.arange(0,d['depth_y'],.08),indexing='ij')
        self.coverage=np.c_[gx.ravel(),gy.ravel(),np.full(gx.size,d['height_z']+.002)];self.coverage_seen=np.full(len(self.coverage),-10**18,np.int64)
        scenario=root/'calibration/scenario.yaml';self.events=yaml.safe_load(scenario.read_text()).get('events',[]) if scenario.exists() else []
        self.changes=[{'actor':e['actor'],'action':e['action'],'scheduled_s':e['at'],'first_visible_ns':None,'adequate_ns':None,'live_ns':None,'suppressed_ns':None,'observations':0,'last_visible_ns':None} for e in self.events if 'actor' in e]
        self.change_support={}
        self.surface_cache=None;self.obsolete_cache={}

    def project(self,t,cam,c,points,depth):
        gt=self.at(t);pose=np.array(gt['cameras'][cam]);local=(points-pose[:3,3])@pose[:3,:3];z=local[:,2];h,w=depth.shape
        if c['model']=='kb4':uv=project_kb(local,w,c['kb4']);distance=np.linalg.norm(local,axis=1)
        else:
            fx=w/(2*np.tan(np.deg2rad(c['horizontal_fov_deg'])/2));uv=local[:,:2]/np.maximum(z[:,None],1e-6)*fx+[(w-1)/2,(h-1)/2];distance=z
        x=np.rint(uv[:,0]).astype(int);y=np.rint(uv[:,1]).astype(int);valid=(z>.05)&(x>=0)&(x<w)&(y>=0)&(y<h)
        measured=np.zeros(len(points));ids=np.flatnonzero(valid);measured[ids]=depth[y[ids],x[ids]];valid&=measured>.05
        return valid,measured-distance

    def observe(self,frame,c):
        t=frame.t_capture_ns
        if t-self.last_observe.get(frame.cam_id,0)<150_000_000:return
        depth=frame.depth
        if frame.cam_id=='head_left':
            path=self.gt_depth.get(frame.seq)
            if not path:return
            depth=np.load(path)['depth'].astype(np.float32)
            if depth.shape!=frame.rgb.shape[:2]:
                import cv2
                depth=cv2.resize(depth,(frame.width,frame.height),interpolation=cv2.INTER_NEAREST)
        if depth is None or frame.cam_id=='head_right':return
        self.last_observe[frame.cam_id]=t
        valid,delta=self.project(t,frame.cam_id,c,self.coverage,depth);self.coverage_seen[valid&(np.abs(delta)<.025)]=t
        gt=self.at(t)
        for change in self.changes:
            name=change['actor'];a=np.array(self.initial['objects'][name]);b=np.array(gt['objects'][name])
            if np.allclose(a,b,atol=.005):continue
            current=trimesh.transform_points(self.samples[name],b);old=trimesh.transform_points(self.samples[name],a)
            vc,dc=self.project(t,frame.cam_id,c,current,depth);vo,do=self.project(t,frame.cam_id,c,old,depth)
            useful=(vc&(np.abs(dc)<.025)).sum()>=3 or (vo&(do>.035)).sum()>=3
            if useful:
                change['observations']+=1;change['last_visible_ns']=int(t)
                if change['first_visible_ns'] is None:change['first_visible_ns']=int(t)
                key=(name,change['scheduled_s']);support=self.change_support.setdefault(key,{'visible':np.zeros(len(current),bool),'free':set(),'pose':None})
                support['visible']|=vc&(np.abs(dc)<.025)
                pose_key=tuple(np.round(b[:3,3],3))
                if support['pose']!=pose_key:
                    oldmesh=self.parts[name].copy();oldmesh.apply_transform(a);bounds=oldmesh.bounds+np.array([[-.025]*3,[.025]*3]);scan=self.view.splats.centers
                    ids=np.flatnonzero(((scan>=bounds[0])&(scan<=bounds[1])).all(1)) if a[2,3]>-1 else np.array([],int)
                    if len(ids):
                        mesh,_,_=self.current(t);ids=ids[trimesh.proximity.closest_point(mesh,scan[ids])[1]>.02]
                    support['obsolete_ids']=ids;support['pose']=pose_key
                ids=support['obsolete_ids']
                if len(ids):
                    vi,di=self.project(t,frame.cam_id,c,self.view.splats.centers[ids],depth)
                    support['free'].update(ids[vi&(di>.035)].tolist())
                    adequate_fraction=sum(int(i) in support['free'] for i in ids)/len(ids)
                    change['obsolete_free_observation_fraction']=adequate_fraction
                    enough=adequate_fraction>=.8
                else:enough=float(support['visible'].mean())>=.25
                change['visible_surface_sample_fraction']=float(support['visible'].mean())
                if change['observations']>=3 and enough and change['adequate_ns'] is None:change['adequate_ns']=int(t)

    def at(self,t):
        i=np.clip(np.searchsorted(self.times,t,side='right')-1,0,len(self.truth)-1)
        return self.truth[i]

    def current(self,t):
        gt=self.at(t);parts=[];samples=[];names=[]
        key=json.dumps(gt['objects'],sort_keys=True)
        if self.surface_cache and self.surface_cache[0]==key:return self.surface_cache[1]
        for name,mesh in self.parts.items():
            if name=='floor':transform=np.eye(4)
            elif name in gt['objects']:transform=np.array(gt['objects'][name])
            else:continue
            if transform[2,3]<-1:continue
            m=mesh.copy();m.apply_transform(transform);parts.append(m)
            samples.append(trimesh.transform_points(self.samples[name],transform));names.extend([name]*len(samples[-1]))
        result=trimesh.util.concatenate(parts),np.concatenate(samples),np.array(names)
        self.surface_cache=(key,result)
        return result

    def visibility(self,t,points,depth,k):
        gt=self.at(t);pose=np.array(gt['cameras']['head_left']);local=(points-pose[:3,3])@pose[:3,:3]
        z=local[:,2];uv=local[:,:2]/np.maximum(z[:,None],1e-6)*k[0,0]+k[:2,2]
        x=np.rint(uv[:,0]).astype(int);y=np.rint(uv[:,1]).astype(int);h,w=depth.shape
        valid=(z>.05)&(x>=0)&(x<w)&(y>=0)&(y<h)
        ids=np.flatnonzero(valid);visible=np.zeros(len(points),bool)
        visible[ids]=np.abs(depth[y[ids],x[ids]]-z[ids])<.025
        return visible

    def evaluate(self,t,displayed=None,full=True):
        mesh,samples,names=self.current(t)
        if displayed is not None:points=displayed['points'];hit_ns=displayed['hit_ns']
        else:
            points,colors,ages,sources=self.map.points(t);hit_ns=(t-ages.astype(np.float64)*1e9).astype(np.int64)
        minimum=np.array(self.map.cfg['workspace_min']);maximum=np.array(self.map.cfg['workspace_max'])
        roi=((samples>=minimum)&(samples<maximum)).all(1);samples=samples[roi];names=names[roi]
        # Exclude undersides enclosed by the solid block and below-ground surfaces.
        d=self.cfg['desk'];interior=(samples[:,0]>0)&(samples[:,0]<d['width_x'])&(samples[:,1]>0)&(samples[:,1]<d['depth_y'])&(samples[:,2]<d['height_z']-.015)
        keep=~interior;samples=samples[keep];names=names[keep]
        if displayed is None:self.mask.update(t)
        else:self.mask.states=displayed['old_states']
        old=self.view.splats.centers;fused_old=old[self.mask.states!=2]
        modes={'old_only':old,'live_only':points,'fused':np.concatenate([fused_old,points])}
        scores={};threshold=.02
        # Changed regions are actor bounding boxes expanded by one voxel.
        changed=np.zeros(len(samples),bool);changed_boxes=[];gt=self.at(t)
        for name in ['box','mug','new_mug','chair']:
            a=np.array(self.initial['objects'][name]);b=np.array(gt['objects'][name])
            if not np.allclose(a,b,atol=.005):
                for transform in [a,b]:
                    if transform[2,3]<-1:continue
                    m=self.parts[name].copy();m.apply_transform(transform);changed_boxes.append(m.bounds+np.array([[-.03]*3,[.03]*3]))
        def in_changed(p):
            inside=np.zeros(len(p),bool)
            for bounds in changed_boxes:inside|=((p>=bounds[0])&(p<=bounds[1])).all(1)
            return inside
        changed=in_changed(samples)
        for mode,shown in (modes.items() if full else []):
            if len(shown):
                # Exact triangle distance measures false geometry; sample tree measures completeness.
                distance=trimesh.proximity.closest_point(mesh,shown[::max(1,len(shown)//12000)])[1]
                nearest=cKDTree(shown).query(samples,workers=1)[0]
                sample_shown=shown[::max(1,len(shown)//12000)];cm=in_changed(sample_shown)
                recall=float((nearest[changed]<=threshold).mean()) if changed.any() else None
                precision=float((distance[cm]<=threshold).mean()) if cm.any() else None
                f1=2*precision*recall/(precision+recall) if precision is not None and recall is not None and precision+recall else (0. if precision is not None and recall is not None else None)
                # Duplicate surface support at a distinct location beyond tolerance is included in false geometry.
                scores[mode]={'completeness':float((nearest<=threshold).mean()),'false_or_stale_fraction':float((distance>threshold).mean()),'changed_precision':precision,'changed_recall':recall,'changed_f1':f1,'shown_points':len(shown)}
                scores[mode]['duplicate_cross_layer_fraction']=float((cKDTree(fused_old).query(points)[0]<=.02).mean()) if mode=='fused' and len(points) and len(fused_old) else 0.
            else:scores[mode]={'completeness':0.,'false_or_stale_fraction':None,'changed_precision':None,'changed_recall':0. if changed.any() else None,'changed_f1':0. if changed.any() else None,'shown_points':0}
        exact=trimesh.proximity.closest_point(mesh,points[::max(1,len(points)//6000)])[1] if full and len(points) else np.array([])
        known=np.array([],bool);expected=known
        if full and displayed is None:
            idx,valid=self.map.index(torch.as_tensor(self.coverage,device=self.map.device,dtype=torch.float32));indices=idx.clamp(0,self.map.n-1)
            known=((t-self.map.last_seen[indices])<=int(self.map.cfg['live_seconds']*1e9)).cpu().numpy()&valid.cpu().numpy()
        if full and displayed is not None:
            assert np.allclose(displayed['coverage'],self.coverage,atol=1e-5)
            known=~displayed['unknown']
        if full:expected=(t-self.coverage_seen>=0)&(t-self.coverage_seen<=int(self.map.cfg['live_seconds']*1e9))
        for change in self.changes:
            if change['first_visible_ns'] is None:continue
            name=change['actor'];a=np.array(self.initial['objects'][name]);b=np.array(gt['objects'][name]);current=trimesh.transform_points(self.samples[name],b)
            fresh=points[hit_ns>=change['first_visible_ns']]
            # Presence is distinct from whole-object surface completeness. The
            # operating map filters for repeated hits before sending these voxels.
            plane=self.mask.clusters.plane_z if self.mask.clusters else d['height_z']
            support_z=plane if current[:,2].max()>plane+.025 else 0.
            eligible=fresh[fresh[:,2]>support_z+.025]
            matching=eligible[cKDTree(current).query(eligible)[0]<=.02] if len(eligible) else eligible
            change['present_surface_voxels']=len(matching)
            if (b[2,3]>-1 and len(matching)>=3 and self.map.cfg.get('live_min_hits',1)>=3
                    and change.get('presence_ns') is None):change['presence_ns']=int(t)
            if b[2,3]>-1 and len(fresh) and change['live_ns'] is None:
                support=(cKDTree(fresh).query(current)[0]<=.02).mean()
                change['strict_live_surface_fraction']=float(support)
                if support>=.25:change['live_ns']=int(t)
            if a[2,3]>-1:
                oldmesh=self.parts[name].copy();oldmesh.apply_transform(a);bounds=oldmesh.bounds+np.array([[-.025]*3,[.025]*3])
                oldids=((old>=bounds[0])&(old<=bounds[1])).all(1)
                # Count only old scan support no longer on the current actor surface.
                cache_key=(name,self.surface_cache[0])
                if cache_key not in self.obsolete_cache:
                    ids=np.flatnonzero(oldids)
                    if len(ids):
                        obsolete=trimesh.proximity.closest_point(mesh,old[ids])[1]>.02
                        ids=ids[obsolete]
                    self.obsolete_cache[cache_key]=ids
                ids=self.obsolete_cache[cache_key]
                if len(ids) and (self.mask.states[ids]==2).mean()>=.8 and change['suppressed_ns'] is None:change['suppressed_ns']=int(t)
                change['obsolete_scan_samples']=len(ids)
        return {'t_ns':int(t),'modes':scores,'live_surface_error_m':{'n':len(exact),'median':float(np.median(exact)) if len(exact) else None,'p95':float(np.percentile(exact,95)) if len(exact) else None},
            'unknown_visibility_accuracy':float((known==expected).mean()) if len(known) else None,'visibility_expected_known_fraction':float(expected.mean()) if len(known) else None,
            'old_suppressed_fraction':float((self.mask.states==2).mean()),'live_points':len(points)}
