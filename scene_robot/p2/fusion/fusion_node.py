"""Observation-only geometry pipeline hosted with the operator UI."""
import json
from dataclasses import replace
from pathlib import Path
import numpy as np
import yaml
from p2.clock import now_ns
from p2.fusion.tf_buffer import TransformBuffer
from p2.fusion.voxel_map import VoxelMap
from p2.fusion.stereo import Stereo
from p2.scene.load_splat import load
from p2.camera_geometry import rays_kb


class Fusion:
    def __init__(self,cameras,config='configs/fusion.yaml',log='data/logs/fusion_latest.jsonl',publish=False,clock=now_ns,observation_sink=None):
        from p2.bus import Publisher
        self.publisher=Publisher('tcp://127.0.0.1:5602') if publish else None
        self.clock=clock
        # Optional read-only display consumer. Absent in offline map evaluation.
        self.observation_sink=observation_sink
        self.cameras=cameras;self.cfg=yaml.safe_load(Path(config).read_text());self.tf=TransformBuffer(self.cfg['max_age_ms']);self.map=VoxelMap(self.cfg)
        if Path('assets/scan/old_map.ply').exists():self.map.set_prior(load('assets/scan/old_map.ply').centers)
        self.log=open(log,'w');self.latest_capture=0;self.integrations=0;self.rays={};self.pairs={};self.stereo=None;self.last_color={};self.last_stereo=None
        for n,c in cameras.items():
            h,w=c['height'],c['width'];y,x=np.mgrid[:h,:w];fx=w/(2*np.tan(np.deg2rad(c.get('horizontal_fov_deg',120))/2))
            if c['model']=='kb4':self.rays[n]=rays_kb(w,c['kb4'])[0]
            else:self.rays[n]=np.stack([(x-(w-1)/2)/fx,(y-(h-1)/2)/fx,np.ones_like(x)],-1).astype(np.float32)
            if n=='head_left':self.stereo=Stereo(fx)

    def integrate(self,frame,received):
        self.integration_start=self.clock()
        confidence=None;sync=1.;sync_info={}
        original=frame
        if frame.cam_id in ('head_left','head_right') and self.cameras['head_left']['depth_mode']=='sgbm':
            pair=self.pairs.setdefault(frame.seq,{})
            pair[frame.cam_id]=(frame,received)
            if len(self.pairs)>8:self.pairs.pop(min(self.pairs))
            if len(pair)<2:return self._log(frame,received,False,'waiting for matching stereo exposure')
            (left,left_received),(right,right_received)=pair['head_left'],pair['head_right'];self.pairs.pop(frame.seq,None)
            received=left_received
            depth,confidence,sync_info=self.stereo.compute(left.rgb,right.rgb,(left.t_capture_ns-right.t_capture_ns)/1e6)
            if depth is None:return self._log(left,received,False,sync_info['reason'],sync=sync_info)
            self.last_stereo=(left.seq,depth)
            frame=replace(left,depth=depth,depth_kind='sgbm');sync=sync_info['sync_weight']
        start=self.clock();c=self.cameras[frame.cam_id]
        if frame.cam_id not in self.cfg['geometry_cameras'] or frame.depth is None:
            self.last_color[frame.cam_id]=frame.t_capture_ns
            return self._log(frame,received,False,'colour coverage only; no geometry')
        if frame.depth_kind not in ('sim_ideal','sgbm'):return self._log(frame,received,False,'unsupported depth contract')
        try:
            t=frame.t_capture_ns if self.cfg['pose_time']=='capture' else received
            pose,uncertainty=self.tf.pose(c['frame'],t,self.cfg['timestamp_uncertainty_ms'])
            age=max(0,(start-frame.t_capture_ns)/1e6)
            if age>self.cfg['max_age_ms']:return self._log(frame,received,False,'too old')
            stride=self.cfg['pixel_stride'];phase=frame.seq//self.cfg.get('sample_repeat',1)
            sx=phase%stride;sy=(phase//stride)%stride
            sample=(slice(sy,None,stride),slice(sx,None,stride))
            depth=frame.depth[sample];rays=self.rays[frame.cam_id][sample];rgb=frame.rgb[sample]
            valid=(depth>.05)&(depth<self.cfg['max_range_m'])
            if c['model']=='kb4':valid&=rays[...,2]>=0
            if confidence is not None:valid&=confidence[sample]>.35
            local=rays[valid]*depth[valid,None];world=local@pose[:3,:3].T+pose[:3,3]
            age_weight=np.exp(-age/500);pose_weight=np.exp(-uncertainty['linear_m']/.02-uncertainty['angular_rad']/.05)
            sensor_weight=.8 if frame.depth_kind=='sim_ideal' else 1.
            weight=float(age_weight*pose_weight*sensor_weight)
            ray_weights=1/(1+(depth[valid]/2)**2)
            if confidence is not None:ray_weights*=confidence[sample][valid]
            result=self.map.integrate(pose[:3,3],world,rgb[valid],frame.t_capture_ns,weight,1<<list(self.cameras).index(frame.cam_id),ray_weights)
            self.latest_capture=frame.t_capture_ns;self.integrations+=1
            display_start=self.clock()
            if self.observation_sink is not None:
                self.observation_sink(frame,pose,self.rays[frame.cam_id],confidence,1<<list(self.cameras).index(frame.cam_id))
            return self._log(frame,received,True,'integrated',display_sample_ms=(self.clock()-display_start)/1e6,weight=weight,weight_terms={'sensor':sensor_weight,'sync':sync,'pose':pose_weight,'age':float(age_weight),'mean_ray_range_confidence':float(ray_weights.mean()) if len(ray_weights) else 0},pose_uncertainty=uncertainty,sync=sync_info,**result)
        except LookupError as exc:return self._log(frame,received,False,str(exc))

    def _log(self,frame,received,accepted,reason,**kwargs):
        row=dict(cam=frame.cam_id,seq=frame.seq,t_capture_ns=frame.t_capture_ns,t_send_ns=frame.t_send_ns,**frame.timing,t_recv_ns=received,t_integration_start_ns=self.integration_start,t_integrated_ns=self.clock(),accepted=accepted,reason=reason,source=frame.source,**kwargs)
        self.log.write(json.dumps(row)+'\n');self.log.flush()
        if self.publisher:
            from p2.msgs import Status
            self.publisher.send('fusion/meta',Status(now_ns(),row))
        return row

    def close(self):
        self.map.save('data/logs/fusion_latest.npz');self.log.close()
        if self.publisher:self.publisher.close()

