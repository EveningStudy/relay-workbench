"""Offline presentation replay UI; not the latency-approved operating launcher.

Preserves optional display aids and recent-depth experiment after M20 fallback.
Consumes the same received observations; never reads scene truth.
"""
import argparse
from collections import deque
import json
from pathlib import Path
import time
import numpy as np
import viser
from viser.extras import ViserUrdf
import yaml
from p2.bus import Publisher, Subscriber, COMMANDS
from p2.clock import now_ns
from p2.msgs import Command, JointState, Status, DisplayEvidence
from p2.fusion.ingest import Ingest
from p2.robot.ik import nudge
from p2.scene.splat_view import SplatView
from p2.fusion.fusion_node import Fusion
from p2.fusion.splat_mask import SplatMask
from p2.io.record_session import RecordSession
from p2.ui.change_markers import ChangeMarkers,box_segments
from p2.ui import camera_aids
from p2.ui.live_points import RecentLivePoints, Samples
from p2.ui.display_updates import voxel_buffer,MarkerWorker,MarkerNodes


class OperatorUI:
    def __init__(self,cameras='configs/cameras.yaml',fusion_config='configs/fusion.yaml',style_config='configs/m22/presentation_ui.yaml'):
        self.config=yaml.safe_load(Path(cameras).read_text())
        self.config['cameras']['real_phone']={'width':1280,'height':720,'model':'pinhole','depth_mode':'none'}
        self.scene_config=yaml.safe_load(Path('configs/scene.yaml').read_text())
        self.style=yaml.safe_load(Path(style_config).read_text())
        self.phone_pose=None;self.phone_frustum=None;self.phone_overlay_ns=0
        self.server=viser.ViserServer(host='127.0.0.1',port=8090,label='Relay')
        # Pinned viser 1.1.1: the panel label does not set the browser tab title.
        from viser._messages import RunJavascriptMessage
        self.server._websock_server.queue_message(RunJavascriptMessage(source="document.title='Relay · Scene and robot';"))
        self.server.gui.configure_theme(control_width='medium',dark_mode=True)
        self.server.scene.add_grid('/floor',plane='xy',cell_color=(45,45,50),section_color=(65,65,70),cell_thickness=.5,section_thickness=.5)
        self.server.scene.add_frame('/world',axes_length=0.3)
        self.splat_view=SplatView(self.server) if Path('assets/scan/old_map.ply').exists() else None
        self.robot=ViserUrdf(self.server,Path('assets/robot/relay.urdf'),root_node_name='/Relay')
        self.robot_config=yaml.safe_load(Path('configs/robot.yaml').read_text())
        self.robot.update_cfg(self.robot_config['initial'])
        self.joint_names=[];self.q=np.array([]);self.side='left'
        self.low_latency=yaml.safe_load(Path(fusion_config).read_text()).get('low_latency',False)
        self.running=True;self.ui_control=Subscriber('control/ui','tcp://127.0.0.1:5604')
        self.commands=Publisher(COMMANDS);self.ingest=Ingest(self.config['cameras'],1 if self.low_latency else 2)
        self.last_feed={};self.feed_captures={};self.last_mask=0;self.last_robot_q=None;self.last_status=0
        self.coverage_cache={}
        self.coverage_layout=None
        self.fusion=Fusion(self.config['cameras'],config=fusion_config,publish=True);self.last_display=0
        self.recent=RecentLivePoints(self.style['crisp_live'],self.fusion.cfg) if self.style['crisp_live']['enabled'] else None
        if self.recent:self.fusion.observation_sink=self.recent.accept
        self.live_samples=Samples.empty();self.live_telemetry={};self.last_live_upload=None
        self.timing_log=open('data/logs/ui_timing.jsonl','w');self.display_rows={};self.flush_seq=0
        self.mask=SplatMask(self.splat_view,self.fusion.map) if self.splat_view else None
        self.change_detector=ChangeMarkers(self.splat_view.splats.centers,self.mask.clusters,self.fusion.map.res,self.style) if self.mask else None
        self.change_rows=[];self.change_handles=[];self.camera_handles={};self.last_aids=0
        self.marker_worker=MarkerWorker(self.change_detector) if self.change_detector else None
        self.marker_nodes=MarkerNodes();self.marker_worker_ms=0.;self.last_marker_result_ns=0
        self.live=None
        self.cloud_handles={}
        self.header=self.server.gui.add_markdown('# Relay\nProvisional embodiment · '+self.scene_config['label'])
        from p2.io.frozen_build import check
        freeze=check()
        if freeze:self.header.content+='  \nFrozen recording build `'+freeze['build_hash'][:12]+'`'
        self.server.gui.add_button('STOP',color='red').on_click(lambda _:self.send('stop',{}))
        self.record_session=RecordSession(cameras,fusion_config)
        self.episode_name=self.server.gui.add_text('Episode name',initial_value='operator_'+time.strftime('%Y%m%d_%H%M%S'))
        self.record_status=self.server.gui.add_markdown('Recorder ready · operator operator · origin teleop')
        self.record_start=self.server.gui.add_button('Start recording',color='green')
        self.record_stop=self.server.gui.add_button('Stop recording',disabled=True)
        self.record_start.on_click(lambda _:self.start_recording())
        self.record_stop.on_click(lambda _:self.stop_recording())
        self.camera_table=self.server.gui.add_markdown('**Cameras** · waiting for input')
        self.server.gui.add_markdown('**Scene legend**  \nLIVE: occupied voxel proxies · natural image colour  \nOptional recent depth replaces voxel proxies; sparse observed pixels only  \nStale/floor diagnostics hidden by default (toggles below)  \nOld scan verified: recent support  \nOld scan unverified: purple tint  \nRemoved: hidden by free evidence  \nUNKNOWN: purple coverage marks')
        self.state_summary=self.server.gui.add_markdown('Waiting for geometry evidence')
        self.state_toggles={}
        with self.server.gui.add_folder('Layers and camera colours',expand_by_default=False):
            for label in ['LIVE','STALE_LIVE','OLD_MAP_VERIFIED','OLD_MAP_UNVERIFIED','REMOVED','UNKNOWN']:
                initial=self.style['show_stale'] if label=='STALE_LIVE' else label!='REMOVED'
                self.state_toggles[label]=self.server.gui.add_checkbox(label,initial_value=initial)
            self.floor_toggle=self.server.gui.add_checkbox('Floor voxel diagnostics',initial_value=self.style['show_floor'])
            self.depth_toggle=self.server.gui.add_checkbox('Recent depth display (experimental)',initial_value=self.style['crisp_live']['enabled'])
            self.color_by_camera=self.server.gui.add_checkbox('Colour by camera',initial_value=False)
            self.change_toggle=self.server.gui.add_checkbox('Evidence change markers',initial_value=self.style['change_markers'])
            self.camera_toggle=self.server.gui.add_checkbox('Calibrated camera views',initial_value=self.style['show_camera_frustums'])
            self.label_toggle=self.server.gui.add_checkbox('Enlarged aid labels',initial_value=self.style.get('enlarged_labels',False))
            self.tint_old=self.server.gui.add_checkbox('Tint unverified old scan',initial_value=True)
            self.fog=self.server.gui.add_checkbox('Unknown voxel fog',initial_value=False)
            self.server.gui.add_markdown('Camera colours: blue=head · orange=left wrist · pink=right wrist. Multi-source voxels use the highest source bit. REMOVED is an optional red diagnostic.\n\nDROPPING: >20% sequence loss sustained across a window of at least 2 seconds. Freshness queue skips are deliberate, not delivery loss.')
        with self.server.gui.add_folder('Driving keys',expand_by_default=False):
            self.server.gui.add_markdown('WASD: base · Q/E: turn · R/F: lift · T/G: hip\n\nArrows: head · 1–6: arm poses · brackets: select arm · IJKL/UO: Cartesian nudge\n\nBase commands are short pulses with a deadman timeout. Click the canvas before using keys.')
        self.feedback=self.server.gui.add_markdown('Waiting for robot state')
        self.marker=self.server.gui.add_html('<span id="relay-state" data-capture="0" data-joint="0" style="display:none"></span>')
        self.feeds={};self.status={};self.rate={n:deque(maxlen=60) for n in self.config['cameras']}
        for n in self.config['cameras']:
            self.status[n]='OFFLINE'
            with self.server.gui.add_folder(n,expand_by_default=n=='head_left'):
                self.feeds[n]=self.server.gui.add_image(np.zeros((100,160,3),np.uint8),label=n,format='jpeg',jpeg_quality=90)
        with self.server.gui.add_folder('Real phone pose diagnostic',expand_by_default=False):
            self.phone_status=self.server.gui.add_markdown('Real phone: pose unknown · RGB only')
            self.phone_overlay=self.server.gui.add_image(np.zeros((180,320,3),np.uint8),label='Real phone + old scan projection (diagnostic)',format='jpeg',jpeg_quality=90)
        keys=['W','S','A','D','Q','E','R','F','T','G','arrowleft','arrowright','arrowup','arrowdown','1','2','3','4','5','6','[',']','I','K','J','L','U','O','space']
        for key in keys:self.server.gui.add_command('Teleop '+key,hotkey=key).on_trigger(lambda _,k=key:self.key(k))
        self.server.initial_camera.position=(2.7,-1.5,2.5)
        self.server.initial_camera.look_at=(1.3,.7,.85)
        self.server.initial_camera.up_direction=(0,0,1)
        self.last_joint_ns=0;self.last_capture_ns=0;self.frames=0

    def send(self,action,values):self.commands.send('command',Command(now_ns(),action,values))

    def start_recording(self):
        try:
            path=self.record_session.start(self.episode_name.value)
            self.record_start.disabled=True;self.record_stop.disabled=False;self.episode_name.disabled=True
            self.record_status.content='Recording to '+path+' · click canvas once to drive'
        except ValueError as e:self.record_status.content=str(e)

    def stop_recording(self):
        self.send('stop',{});self.send('record_stop',{})
        self.record_session.close()
        path=self.record_session.path
        self.record_status.content=('Saved '+str(path)) if path and (path/'meta.json').exists() else 'Recorder failed; see data/logs/teleop_recorder.txt'
        self.record_start.disabled=False;self.record_stop.disabled=True;self.episode_name.disabled=False

    def cloud(self,name,points,colors,**kwargs):
        # Viser's client cannot build a valid bounding sphere for an empty cloud.
        # Hide the previous layer without inventing any placeholder geometry.
        if not len(points):
            handle=self.cloud_handles.get(name)
            if handle:handle.visible=False
            return handle
        handle=self.cloud_handles.get(name)
        if handle is not None:
            # Pinned viser 1.1.1 property setters snapshot changed arrays and
            # preserve the client node; avoid recreating it on every revocation.
            handle.points=points;handle.colors=np.asarray(colors,dtype=np.uint8)
            for key,value in kwargs.items():setattr(handle,key,value)
            return handle
        handle=self.server.scene.add_point_cloud(name,points,colors,**kwargs)
        self.cloud_handles[name]=handle;return handle

    def surfels(self,name,points,colors,size,visible):
        # One small isotropic Gaussian per existing occupied voxel. No new
        # samples, surface fitting, normals, or geometry enter the map.
        if not len(points):
            if name in self.cloud_handles:self.cloud_handles[name].visible=False
            return
        handle=self.cloud_handles.get(name)
        capacity=max(8192,1<<(len(points)-1).bit_length(),len(handle.buffer) if handle is not None else 0)
        buffer=voxel_buffer(points,colors,size,capacity)
        if handle is None:
            # Fixed-capacity transparent storage slots avoid Viser recreating the
            # entire 216k-prior mesh/material whenever occupied count changes.
            # Active prefix is exact E2 geometry; zero-alpha tail never displays.
            positions=np.zeros((capacity,3),np.float32);positions[:len(points)]=points
            rgba=np.zeros((capacity,4),np.float32);rgba[:len(points),:3]=colors.astype(np.float32)/255;rgba[:len(points),3]=.85
            covariance=np.broadcast_to(np.eye(3,dtype=np.float32)*size**2,(capacity,3,3))
            handle=self.server.scene.add_gaussian_splats(name,positions,covariance,rgba[:,:3],rgba[:,3:],visible=visible)
            self.cloud_handles[name]=handle
        else:
            if not np.array_equal(handle.buffer,buffer):handle.buffer=buffer
            handle.visible=visible

    def key(self,key):
        if key in ('space','STOP'):self.send('stop',{});return
        if key in ('[',']'):self.side='left' if key=='[' else 'right';return
        velocities={'W':[0,.20,0],'S':[0,-.20,0],'A':[-.20,0,0],'D':[.20,0,0],'Q':[0,0,.3],'E':[0,0,-.3]}
        if key in velocities:self.send('velocity',{'velocity':velocities[key]});return
        if not len(self.q):return
        updates={}
        mapping={'R':('lift',.025),'F':('lift',-.025),'T':('hip_pitch',.04),'G':('hip_pitch',-.04),'arrowleft':('head_pan',.05),'arrowright':('head_pan',-.05),'arrowup':('head_tilt',-.05),'arrowdown':('head_tilt',.05)}
        if key in mapping:
            n,d=mapping[key];updates[n]=float(self.q[self.joint_names.index(n)]+d)
        if key in '123456':
            preset=int(key);updates={self.side+'_shoulder_pitch':-.2-.2*(preset%3),self.side+'_elbow':-.4-.3*(preset%3),self.side+'_shoulder_roll':(-.4 if self.side=='left' else .4)*(preset//3)}
        nudges={'I':[.02,0,0],'K':[-.02,0,0],'J':[0,.02,0],'L':[0,-.02,0],'U':[0,0,.02],'O':[0,0,-.02]}
        if key in nudges:updates=nudge(self.joint_names,self.q,self.side,nudges[key])
        if updates:self.send('joints',updates)

    def sync_live_mode(self):
        # Apply GUI state on the integration thread, not a Viser callback thread.
        # Disabling releases history and its observation callback: no hidden cost.
        enabled=self.depth_toggle.value
        if enabled==bool(self.recent):return
        self.recent=RecentLivePoints(self.style['crisp_live'],self.fusion.cfg) if enabled else None
        self.fusion.observation_sink=self.recent.accept if enabled else None
        self.live_samples=Samples.empty();self.live_telemetry={};self.last_live_upload=None
        for name in ('/live_depth','/live','/floor_live'):
            if name in self.cloud_handles:self.cloud_handles[name].visible=False
        self.last_display=0

    def update_aids(self,now,points,live,sources):
        """Optional presentation work; disabled markers do not enqueue jobs."""
        costs={}
        if not self.style.get('diagnostic_skip_aids',False) and now-self.last_aids>self.style['marker_period_s']*1e9:
            self.last_aids=now;phase=now_ns()
            if self.change_toggle.value and self.marker_worker:
                self.marker_worker.submit(points,live,sources,self.mask.states,self.mask.cluster_trace,self.live_samples.points)
            costs['marker_snapshot_submit']=(now_ns()-phase)/1e6;phase=now_ns()
            if self.camera_toggle.value:
                camera_aids.update(self.server,self.fusion.tf,self.ingest.latest,self.config['cameras'],self.camera_handles)
            costs['camera_outlines_labels']=(now_ns()-phase)/1e6
        if not self.camera_toggle.value:
            for handles in self.camera_handles.values():
                for handle in handles:handle.visible=False
        for _,label in self.camera_handles.values():
            label.font_screen_scale=.8 if self.label_toggle.value else .6
        if self.marker_worker:
            completed=self.marker_worker.poll()
            if completed is not None:
                self.change_rows,self.marker_worker_ms=completed;self.last_marker_result_ns=now_ns()
            scale=self.style['marker_label_scale'] if self.label_toggle.value else .65
            # Retain existing nodes while hidden; no new hidden nodes are built.
            if self.change_toggle.value:
                costs.update(self.marker_nodes.update(self.server.scene,self.change_rows,True,scale))
            else:
                for line,label,_ in self.marker_nodes.nodes.values():line.visible=False;label.visible=False
        return costs

    def step(self):
        control=self.ui_control.recv(0)
        if control and control[1].action=='shutdown':self.running=False;return
        self.sync_live_mode()
        step_start=now_ns();displayed=False
        latest=None
        while self.ingest.states:
            try:state=self.ingest.states.popleft()
            except IndexError:break
            if isinstance(state,Status):
                if 'cam_id' in state.values:
                    self.phone_pose=state.values;pose=state.values.get('pose')
                    self.phone_status.content='Real phone: '+(f"board pose · RMS {pose['rms_px']:.2f} px · RGB only" if pose else 'pose unknown · '+str(state.values.get('reason')))
                    if not pose and self.phone_frustum:self.phone_frustum.visible=False
                continue
            self.fusion.tf.add(state)
            if isinstance(state,JointState):
                latest=state
        if latest is not None:
            self.joint_names,self.q=latest.names,latest.q;self.last_joint_ns=latest.t_ns
            if not self.low_latency or self.last_robot_q is None or np.max(np.abs(latest.q-self.last_robot_q))>1e-5:
                self.robot.update_cfg(dict(zip(latest.names,latest.q)));self.last_robot_q=latest.q.copy()
        now=now_ns()
        ingest_start=now
        with self.server.atomic():
            for frame,received in self.ingest.ready():
                row=self.fusion.integrate(frame,received)
                if row and row['accepted']:self.display_rows[row['cam']]=row
                if not self.low_latency or now-self.last_feed.get(frame.cam_id,0)>100_000_000:
                    self.feeds[frame.cam_id].image=frame.rgb;self.last_feed[frame.cam_id]=now;self.feed_captures[frame.cam_id]={'seq':frame.seq,'t_capture_ns':frame.t_capture_ns}
                self.frames+=1
                if frame.cam_id=='real_phone' and self.phone_pose and self.phone_pose['seq']==frame.seq and self.phone_pose.get('pose'):
                    from scipy.spatial.transform import Rotation
                    pose=self.phone_pose['pose'];t=np.array(pose['T_world_camera']);k=np.array(self.phone_pose['camera_matrix'])
                    self.phone_frustum=self.server.scene.add_camera_frustum('/real_phone',fov=2*np.arctan(frame.height/(2*k[1,1])),aspect=frame.width/frame.height,scale=.25,wxyz=Rotation.from_matrix(t[:3,:3]).as_quat(scalar_first=True),position=t[:3,3],image=frame.rgb)
                    if self.splat_view and now-self.phone_overlay_ns>1e9:
                        splats=self.splat_view.splats;pc=(splats.centers[::4]-t[:3,3])@t[:3,:3]
                        uv=pc[:,:2]/np.maximum(pc[:,2:3],.001)*np.diag(k)[:2]+k[:2,2]
                        valid=(pc[:,2]>.05)&(uv[:,0]>0)&(uv[:,0]<frame.width)&(uv[:,1]>0)&(uv[:,1]<frame.height)
                        ids=np.flatnonzero(valid);ids=ids[np.argsort(pc[ids,2])[::-1]];pixels=uv[ids].astype(int);blend=frame.rgb.copy()
                        blend[pixels[:,1],pixels[:,0]]=np.uint8(.5*blend[pixels[:,1],pixels[:,0]]+.5*splats.rgb[::4][ids]*255)
                        self.phone_overlay.image=blend;self.phone_overlay_ns=now
                self.rate[frame.cam_id].append(frame.t_capture_ns);self.last_capture_ns=max(self.last_capture_ns,frame.t_capture_ns)
                if self.low_latency and now_ns()-ingest_start>16_000_000:break
            if now-self.last_display>1e9/self.fusion.cfg['display_hz']:
                displayed=True;display_start=now_ns()
                costs={};phase=now_ns()
                points,colors,ages,sources=self.fusion.map.points(now)
                costs['map_readback']=(now_ns()-phase)/1e6
                live=ages<=self.fusion.cfg['live_seconds']
                if self.color_by_camera.value:
                    palette=np.array([[30,180,255],[80,240,80],[255,160,20],[255,60,170]],np.uint8)
                    colors=palette[np.maximum(0,np.floor(np.log2(np.maximum(sources,1))).astype(int))%4]
                floor=points[:,2]<self.style['floor_height_m']
                if self.recent:
                    dense_start=now_ns()
                    self.live_samples,refreshed=self.recent.select(now,points[live],self.style['floor_height_m'],self.floor_toggle.value)
                    dense=self.live_samples;dense_colors=dense.colors
                    if self.color_by_camera.value:
                        dense_colors=palette[np.maximum(0,np.floor(np.log2(np.maximum(dense.sources,1))).astype(int))%4]
                    upload_key=(self.recent.revision,self.state_toggles['LIVE'].value,self.color_by_camera.value)
                    uploaded=upload_key!=self.last_live_upload
                    if uploaded:
                        self.cloud('/live_depth',dense.points,dense_colors,point_size=self.style['crisp_live']['point_size_m'],
                            point_shape='circle',point_shading='flat',precision='float32',visible=self.state_toggles['LIVE'].value)
                        self.last_live_upload=upload_key
                    self.live_telemetry={**self.recent.telemetry(),'uploaded':uploaded,'refreshed':refreshed,
                        'visible':self.state_toggles['LIVE'].value,'select_upload_ms':(now_ns()-dense_start)/1e6}
                phase=now_ns()
                for name,selection,colour,size,toggle in [
                    ('live',live&~floor,colors,self.style['live_point_m'],'LIVE'),
                    ('stale',~live&~floor,np.full_like(colors,115),self.style['stale_point_m'],'STALE_LIVE'),
                    ('floor_live',live&floor,np.uint8(colors*self.style['floor_brightness']),self.style['floor_point_m'],'LIVE'),
                    ('floor_stale',~live&floor,np.full_like(colors,40),self.style['floor_point_m'],'STALE_LIVE')]:
                    # Never layer voxel proxies on top of recent depth samples.
                    if self.recent and name in ('live','floor_live'):continue
                    visible=self.state_toggles[toggle].value and (not name.startswith('floor_') or self.floor_toggle.value)
                    if not visible:
                        if '/'+name in self.cloud_handles:self.cloud_handles['/'+name].visible=False
                        continue
                    if name in ('live','stale') and not self.style.get('diagnostic_m17_points',False):self.surfels('/'+name,points[selection],colour[selection],size,visible)
                    else:self.cloud('/'+name,points[selection],colour[selection],point_size=size,point_shape=self.style['point_shape'],visible=visible)
                costs['voxel_pack_upload']=(now_ns()-phase)/1e6
                phase=now_ns()
                if self.mask and (not self.low_latency or now-self.last_mask>200_000_000):
                    self.last_mask=now
                    removed=self.mask.update(now,self.state_toggles['OLD_MAP_VERIFIED'].value,self.state_toggles['OLD_MAP_UNVERIFIED'].value,self.tint_old.value)
                    gone=self.splat_view.splats.centers[self.mask.states==2][::15]
                    self.cloud('/removed_evidence',gone,(240,55,55),point_size=.007,visible=self.state_toggles['REMOVED'].value)
                    self.state_summary.content=f'LIVE {int(live.sum())} · STALE_LIVE {int((~live).sum())} · REMOVED Gaussians {removed}'
                costs['mask']=(now_ns()-phase)/1e6
                costs.update(self.update_aids(now,points,live,sources))
                phase=now_ns()
                # Coverage marks are generated from the evidence grid, never scene actors.
                m=self.fusion.map
                import torch
                d=self.scene_config['desk'];w,dep,h=d['width_x'],d['depth_y'],d['height_z']
                if self.coverage_layout is None:
                    gx,gy=np.meshgrid(np.arange(0,w,.08),np.arange(0,dep,.08),indexing='ij')
                    coverage=np.c_[gx.ravel(),gy.ravel(),np.full(gx.size,h+.002)]
                    floor_coverage=coverage.copy();floor_coverage[:,2]=.005
                    idx,_=m.index(torch.tensor(np.concatenate([coverage,floor_coverage]),device=m.device,dtype=torch.float32))
                    self.coverage_layout=(coverage,gx.shape,idx.clamp(0,m.n-1))
                coverage,shape,idx=self.coverage_layout
                # Identical display queries at the same epoch; immutable indices
                # and one combined readback instead of two rebuilt GPU grids.
                both=((now-m.last_seen[idx])>int(self.fusion.cfg['live_seconds']*1e9)).cpu().numpy()
                unknown,floor_unknown=np.split(both,2)
                rgba=np.zeros((*shape,4),np.uint8);rgba[unknown.reshape(shape)]=[145,85,185,65]
                self.coverage_image('/unknown',rgba,shape,w,dep,h+.005)
                floor_rgba=rgba.copy();floor_rgba[:]=0;floor_rgba[floor_unknown.reshape(shape)]=[145,85,185,18]
                self.coverage_image('/unknown_floor',floor_rgba,shape,w,dep,.005)
                if self.fog.value:
                    fogpoints=np.concatenate([coverage[unknown]+[0,0,z] for z in [-.5,-.25,.25,.5]])
                    self.cloud('/unknown_fog',fogpoints,(130,85,180),point_size=.008)
                elif '/unknown_fog' in self.cloud_handles:self.cloud_handles['/unknown_fog'].visible=False
                costs['coverage']=(now_ns()-phase)/1e6
                self.last_display=now
                self.display_ms=(now_ns()-display_start)/1e6
            status_rows=[]
            for n in self.status:
                if n not in self.ingest.latest:continue
                frame,received=self.ingest.latest[n];now=now_ns();age=(now-frame.t_capture_ns)/1e6;transport=(received-frame.t_capture_ns)/1e6
                samples=self.rate[n];fps=(len(samples)-1)*1e9/max(1,samples[-1]-samples[0]) if len(samples)>1 else 0
                from p2.ui.camera_status import delivery_loss,state as health_state
                loss=delivery_loss(self.ingest.arrivals[n],now);state=health_state(now,received,age,loss);self.status[n]=state
                status_rows.append(f'| {n.replace("wrist_","w_").replace("head_","h_")} | {state} | {fps:.0f} | {age:.0f} |')
            if now-self.last_status>250_000_000:
                self.last_status=now
                self.camera_table.content='| Camera | Status | Hz | Age ms |\n|---|---|---:|---:|\n'+'\n'.join(status_rows)
                if len(self.q):self.feedback.content=f'Selected arm: {self.side} · base x {self.q[0]:.3f} · base y {self.q[1]:.3f}'
            if displayed:
                import html
                self.flush_seq+=1;t_flush=now_ns()
                payload={'flush_seq':self.flush_seq,'t_flush_ns':t_flush,'rows':list(self.display_rows.values()),'display_ms':self.display_ms,'step_ms':(t_flush-step_start)/1e6,
                    'display_cost_ms':costs,
                    'marker_worker_ms':self.marker_worker_ms,
                    'feeds':dict(self.feed_captures),'ages':{n:(t_flush-r['t_capture_ns'])/1e6 for n,r in self.feed_captures.items()},
                    'latest_observation_ages':{n:(t_flush-f.t_capture_ns)/1e6 for n,(f,r) in self.ingest.latest.items()},
                    'camera_states':dict(self.status),
                    'change_markers':self.change_rows,'camera_views_visible':self.camera_toggle.value,'render_style':self.style,
                    'change_markers_visible':self.change_toggle.value,'enlarged_labels':self.label_toggle.value,
                    'crisp_live':self.live_telemetry,
                    'live_display_mode':'crisp' if self.recent else 'voxel',
                    'live_voxel_points':int((live&~floor).sum()) if not self.recent and self.state_toggles['LIVE'].value else 0,
                    'last_mask_update_ns':self.last_mask,'last_marker_update_ns':self.last_marker_result_ns,
                    'last_marker_submit_ns':self.last_aids,
                    'phone_pose_state':{'seq':self.phone_pose.get('seq'),'valid':self.phone_pose.get('pose') is not None,
                        'reason':self.phone_pose.get('reason')} if self.phone_pose else None,
                    'latest_observations':{n:{'seq':f.seq,'t_capture_ns':f.t_capture_ns,'t_recv_ns':r}
                        for n,(f,r) in self.ingest.latest.items()}}
                serialized=json.dumps(payload,separators=(',',':'))
                self.marker.content=f'<span id="relay-state" data-capture="{self.fusion.latest_capture}" data-joint="{self.last_joint_ns}" data-y="{float(self.q[1]) if len(self.q) else 0}" data-timing="{html.escape(serialized,quote=True)}" style="display:none"></span>'
                self.timing_log.write(serialized+'\n');self.timing_log.flush()
                if self.fusion.cfg.get('record_display_evidence') and self.fusion.publisher and self.mask:
                    shown=self.live_samples if self.state_toggles['LIVE'].value else Samples.empty()
                    self.fusion.publisher.send('fusion/evidence',DisplayEvidence(t_flush,self.flush_seq,points.astype(np.float32),self.mask.states.copy(),coverage.astype(np.float32),unknown,(now-ages.astype(np.float64)*1e9).astype(np.int64),
                        shown.points if self.recent else None,shown.capture_ns if self.recent else None))
        if displayed:self.server.flush()

    def coverage_image(self,name,rgba,shape,w,depth,z):
        visible=self.state_toggles['UNKNOWN'].value
        old=self.coverage_cache.get(name)
        if old is not None and old[1]==visible and np.array_equal(old[0],rgba):return
        self.server.scene.add_image(name,np.flipud(rgba.transpose(1,0,2)),shape[0]*.08,shape[1]*.08,position=(w/2,depth/2,z),visible=visible,cast_shadow=False,receive_shadow=False)
        self.coverage_cache[name]=(rgba.copy(),visible)

    def close(self):
        if self.marker_worker:self.marker_worker.close()
        if self.record_session.process and self.record_session.process.poll() is None:self.stop_recording()
        self.send('stop',{});self.send('shutdown',{});self.ingest.close();self.commands.close();self.ui_control.close();self.fusion.close();self.timing_log.close();self.server.stop()


def main():
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=float,default=0);p.add_argument('--cameras',default='configs/cameras.yaml');p.add_argument('--fusion',default='configs/fusion.yaml');p.add_argument('--style',default='configs/m22/presentation_ui.yaml');p.add_argument('--cpu-cores',type=int);args=p.parse_args()
    if args.cpu_cores:
        import psutil
        proc=psutil.Process();proc.cpu_affinity(proc.cpu_affinity()[:args.cpu_cores])
    ui=OperatorUI(args.cameras,args.fusion,args.style);start=now_ns()
    try:
        while ui.running and (not args.seconds or (now_ns()-start)/1e9<args.seconds):ui.step();time.sleep(.002 if ui.low_latency else .025)
    finally:
        Path('data/logs/ui_latest.json').write_text(json.dumps({'frames':ui.frames,'overflows':ui.ingest.overflows,'elapsed_s':(now_ns()-start)/1e9},indent=2));ui.close()


if __name__=='__main__':main()
