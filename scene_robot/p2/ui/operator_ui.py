"""M20 operating display restored from 6c3374c; evidence-only telemetry retained.

Newer display aids live in presentation_ui for offline replay captures only.
"""
import argparse
from collections import deque
import json
from pathlib import Path
import time
import threading
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
from p2.ui.teleop_input import KEYBOARD_JS, PresetRamp, joint_limits


class OperatorUI:
    def __init__(self,cameras='configs/cameras.yaml',fusion_config='configs/fusion.yaml'):
        self.config=yaml.safe_load(Path(cameras).read_text())
        self.config['cameras']['real_phone']={'width':1280,'height':720,'model':'pinhole','depth_mode':'none'}
        self.scene_config=yaml.safe_load(Path('configs/scene.yaml').read_text())
        self.phone_pose=None;self.phone_frustum=None;self.phone_overlay_ns=0
        self.server=viser.ViserServer(host='127.0.0.1',port=8090,label='Relay')
        # Pinned viser 1.1.1: the panel label does not set the browser tab title.
        from viser._messages import RunJavascriptMessage
        self.server._websock_server.queue_message(RunJavascriptMessage(source="document.title='Relay · Scene and robot';"))
        self.server.gui.configure_theme(control_width='medium',dark_mode=True)
        self.server.scene.add_grid('/floor',plane='xy')
        self.server.scene.add_frame('/world',axes_length=0.3)
        self.splat_view=SplatView(self.server) if Path('assets/scan/old_map.ply').exists() else None
        self.robot=ViserUrdf(self.server,Path('assets/robot/relay.urdf'),root_node_name='/Relay')
        self.robot_config=yaml.safe_load(Path('configs/robot.yaml').read_text())
        self.robot.update_cfg(self.robot_config['initial'])
        self.joint_names=[];self.q=np.array([]);self.side='left'
        self.teleop_lock=threading.RLock();self.preset=None
        self.teleop_limits=joint_limits();self.last_preset_tick=now_ns()
        self.low_latency=yaml.safe_load(Path(fusion_config).read_text()).get('low_latency',False)
        self.running=True;self.ui_control=Subscriber('control/ui','tcp://127.0.0.1:5604')
        self.commands=Publisher(COMMANDS);self.ingest=Ingest(self.config['cameras'],1 if self.low_latency else 2)
        self.last_feed={};self.feed_captures={};self.last_mask=0;self.last_robot_q=None;self.last_status=0
        self.coverage_cache={}
        self.fusion=Fusion(self.config['cameras'],config=fusion_config,publish=True);self.last_display=0
        self.timing_log=open('data/logs/ui_timing.jsonl','w');self.display_rows={};self.flush_seq=0
        self.mask=SplatMask(self.splat_view,self.fusion.map) if self.splat_view else None
        self.live=None
        self.cloud_handles={}
        self.header=self.server.gui.add_markdown('# Relay\nSimulated robot · '+self.scene_config['label'])
        from p2.io.frozen_build import check
        freeze=check()
        if freeze:self.header.content+='  \nFrozen recording build `'+freeze['build_hash'][:12]+'`'
        self.arm_banner=self.server.gui.add_html(self.arm_banner_html())
        self.server.gui.add_button('STOP',color='red').on_click(lambda _:self.send('stop',{}))
        self.record_session=RecordSession(cameras,fusion_config)
        self.episode_name=self.server.gui.add_text('Episode name',initial_value='operator_'+time.strftime('%Y%m%d_%H%M%S'))
        self.record_status=self.server.gui.add_markdown('Recorder ready · local session · origin teleop')
        if self.record_session.synthetic_acceptance:
            self.record_status.content='SYNTHETIC ACCEPTANCE ONLY · automated operator · not human evidence'
        self.record_start=self.server.gui.add_button('Start recording',color='green')
        self.record_stop=self.server.gui.add_button('Stop recording',disabled=True)
        self.record_start.on_click(lambda _:self.start_recording())
        self.record_stop.on_click(lambda _:self.stop_recording())
        self.camera_table=self.server.gui.add_markdown('**Cameras** · waiting for input')
        self.server.gui.add_markdown('**Scene legend**  \nLIVE: current colour · stale: grey  \nOld scan verified: recent support  \nOld scan unverified: purple tint  \nRemoved: hidden by free evidence  \nUNKNOWN: purple coverage marks')
        self.state_summary=self.server.gui.add_markdown('Waiting for geometry evidence')
        self.state_toggles={}
        with self.server.gui.add_folder('Layers and camera colours',expand_by_default=False):
            for label in ['LIVE','STALE_LIVE','OLD_MAP_VERIFIED','OLD_MAP_UNVERIFIED','REMOVED','UNKNOWN']:
                self.state_toggles[label]=self.server.gui.add_checkbox(label,initial_value=label!='REMOVED')
            self.color_by_camera=self.server.gui.add_checkbox('Colour by camera',initial_value=False)
            self.tint_old=self.server.gui.add_checkbox('Tint unverified old scan',initial_value=True)
            self.fog=self.server.gui.add_checkbox('Unknown voxel fog',initial_value=False)
            self.server.gui.add_markdown('Camera colours: blue=head · orange=left wrist · pink=right wrist. Multi-source voxels use the highest source bit. REMOVED is an optional red diagnostic.\n\nDROPPING: >20% sequence loss sustained across a window of at least 2 seconds. Freshness queue skips are deliberate, not delivery loss.')
        with self.server.gui.add_folder('Driving keys',expand_by_default=False):
            self.server.gui.add_markdown('Hold WASD: base · hold Q/E: turn · release: base stops\n\nR/F: lift · T/G: hip · arrows: head\n\n[: LEFT arm · ]: RIGHT arm · 1–6: selected-arm smooth poses (~1.6 s) · IJKL/UO: Cartesian nudge\n\nSpace / STOP: cancel all motion, including arm ramp. Click canvas before keys; mouse orbit/zoom remains available. Keyboard keys never move the view.')
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
        self.server.gui.add_command('Release base',hotkey='0').on_trigger(lambda _:self.send('velocity',{'velocity':[0,0,0]}))
        self.server._websock_server.queue_message(RunJavascriptMessage(source=KEYBOARD_JS))
        self.server.initial_camera.position=(2.7,-1.5,2.5)
        self.server.initial_camera.look_at=(1.3,.7,.85)
        self.server.initial_camera.up_direction=(0,0,1)
        self.last_joint_ns=0;self.last_capture_ns=0;self.frames=0

    def send(self,action,values):
        with self.teleop_lock:
            if action in ('stop','shutdown'):self.preset=None
            self.commands.send('command',Command(now_ns(),action,values))

    def arm_banner_html(self):
        return ('<div id="relay-selected-arm" style="font-size:24px;font-weight:800;'
                'padding:8px;background:#183c55;color:#fff;border:2px solid #64c8ff">'
                f'{self.side.upper()} ARM SELECTED</div><div>[ Left · ] Right · 1–6 smooth poses</div>')

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
        handle=self.server.scene.add_point_cloud(name,points,colors,**kwargs)
        self.cloud_handles[name]=handle;return handle

    def key(self,key):
        with self.teleop_lock:self._key(key)

    def _key(self,key):
        if key in ('space','STOP'):self.send('stop',{});return
        if key in ('[',']'):
            self.side='left' if key=='[' else 'right'
            self.arm_banner.content=self.arm_banner_html();return
        # Teleop demand only: below the unchanged 1.5 rad/s URDF yaw limit.
        # Existing base drive/ground contact attenuates the old 0.3 request.
        velocities={'W':[0,.20,0],'S':[0,-.20,0],'A':[-.20,0,0],'D':[.20,0,0],'Q':[0,0,1.0],'E':[0,0,-1.0]}
        if key in velocities:self.send('velocity',{'velocity':velocities[key]});return
        if not len(self.q):return
        updates={}
        mapping={'R':('lift',.025),'F':('lift',-.025),'T':('hip_pitch',.04),'G':('hip_pitch',-.04),'arrowleft':('head_pan',.05),'arrowright':('head_pan',-.05),'arrowup':('head_tilt',-.05),'arrowdown':('head_tilt',.05)}
        if key in mapping:
            n,d=mapping[key];updates[n]=float(self.q[self.joint_names.index(n)]+d)
        if key in '123456':
            preset=int(key);updates={self.side+'_shoulder_pitch':-.2-.2*(preset%3),self.side+'_elbow':-.4-.3*(preset%3),self.side+'_shoulder_roll':(-.4 if self.side=='left' else .4)*(preset//3)}
            start={n:float(self.q[self.joint_names.index(n)]) for n in updates}
            self.preset=PresetRamp(start,updates,self.teleop_limits)
            self.last_preset_tick=now_ns();return
        nudges={'I':[.02,0,0],'K':[-.02,0,0],'J':[0,.02,0],'L':[0,-.02,0],'U':[0,0,.02],'O':[0,0,-.02]}
        if key in nudges:updates=nudge(self.joint_names,self.q,self.side,nudges[key])
        if updates:
            self.preset=None;self.send('joints',updates)

    def tick_preset(self):
        with self.teleop_lock:
            now=now_ns();dt=(now-self.last_preset_tick)/1e9;self.last_preset_tick=now
            if self.preset is None:return
            self.send('joints',self.preset.advance(dt))
            if self.preset.done:self.preset=None

    def step(self):
        control=self.ui_control.recv(0)
        if control and control[1].action=='shutdown':self.running=False;return
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
        self.tick_preset()
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
                points,colors,ages,sources=self.fusion.map.points(now)
                live=ages<=self.fusion.cfg['live_seconds']
                if self.color_by_camera.value:
                    palette=np.array([[30,180,255],[80,240,80],[255,160,20],[255,60,170]],np.uint8)
                    colors=palette[np.maximum(0,np.floor(np.log2(np.maximum(sources,1))).astype(int))%4]
                self.live=self.cloud('/live',points[live],colors[live],point_size=.018,visible=self.state_toggles['LIVE'].value)
                self.cloud('/stale',points[~live],np.full((sum(~live),3),115,np.uint8),point_size=.014,visible=self.state_toggles['STALE_LIVE'].value)
                if self.mask and (not self.low_latency or now-self.last_mask>200_000_000):
                    self.last_mask=now
                    removed=self.mask.update(now,self.state_toggles['OLD_MAP_VERIFIED'].value,self.state_toggles['OLD_MAP_UNVERIFIED'].value,self.tint_old.value)
                    gone=self.splat_view.splats.centers[self.mask.states==2][::15]
                    self.cloud('/removed_evidence',gone,(240,55,55),point_size=.007,visible=self.state_toggles['REMOVED'].value)
                    self.state_summary.content=f'LIVE {int(live.sum())} · STALE_LIVE {int((~live).sum())} · REMOVED Gaussians {removed}'
                # Coverage marks are generated from the evidence grid, never scene actors.
                m=self.fusion.map
                import torch
                d=self.scene_config['desk'];w,dep,h=d['width_x'],d['depth_y'],d['height_z']
                gx,gy=np.meshgrid(np.arange(0,w,.08),np.arange(0,dep,.08),indexing='ij')
                coverage=np.c_[gx.ravel(),gy.ravel(),np.full(gx.size,h+.002)]
                idx,valid=m.index(torch.tensor(coverage,device=m.device,dtype=torch.float32))
                unknown=((now-m.last_seen[idx.clamp(0,m.n-1)])>int(self.fusion.cfg['live_seconds']*1e9)).cpu().numpy()
                rgba=np.zeros((*gx.shape,4),np.uint8);rgba[unknown.reshape(gx.shape)]=[145,85,185,65]
                self.coverage_image('/unknown',rgba,gx.shape,w,dep,h+.005)
                floor_coverage=coverage.copy();floor_coverage[:,2]=.005
                fi,fv=m.index(torch.tensor(floor_coverage,device=m.device,dtype=torch.float32))
                floor_unknown=((now-m.last_seen[fi.clamp(0,m.n-1)])>int(self.fusion.cfg['live_seconds']*1e9)).cpu().numpy()
                floor_rgba=rgba.copy();floor_rgba[:]=0;floor_rgba[floor_unknown.reshape(gx.shape)]=[145,85,185,45]
                self.coverage_image('/unknown_floor',floor_rgba,gx.shape,w,dep,.005)
                if self.fog.value:
                    fogpoints=np.concatenate([coverage[unknown]+[0,0,z] for z in [-.5,-.25,.25,.5]])
                    self.cloud('/unknown_fog',fogpoints,(130,85,180),point_size=.008)
                elif '/unknown_fog' in self.cloud_handles:self.cloud_handles['/unknown_fog'].visible=False
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
                if len(self.q):self.feedback.content=f'Selected arm: {self.side} · base x {self.q[0]:.3f} · base y {self.q[1]:.3f} · yaw {np.degrees(self.q[self.joint_names.index("base_yaw")]):.1f}°'
            if displayed:
                import html
                self.flush_seq+=1;t_flush=now_ns()
                payload={'flush_seq':self.flush_seq,'t_flush_ns':t_flush,'rows':list(self.display_rows.values()),'display_ms':self.display_ms,'step_ms':(t_flush-step_start)/1e6,
                    'feeds':dict(self.feed_captures),'ages':{n:(t_flush-r['t_capture_ns'])/1e6 for n,r in self.feed_captures.items()},
                    'latest_observation_ages':{n:(t_flush-f.t_capture_ns)/1e6 for n,(f,r) in self.ingest.latest.items()},
                    # Evidence-only additions: same flush epoch/atomic marker,
                    # no changes to M20 geometry, integration or mask scheduling.
                    'camera_states':dict(self.status),'live_display_mode':'voxel',
                    'live_voxel_points':int(live.sum()) if self.state_toggles['LIVE'].value else 0,
                    'crisp_live':{},'change_markers':[],'camera_views_visible':False,
                    'change_markers_visible':False,'enlarged_labels':False,
                    'display_backend':'m20_points','last_mask_update_ns':self.last_mask,
                    'phone_pose_state':{'seq':self.phone_pose.get('seq'),'valid':self.phone_pose.get('pose') is not None,
                        'reason':self.phone_pose.get('reason')} if self.phone_pose else None,
                    'latest_observations':{n:{'seq':f.seq,'t_capture_ns':f.t_capture_ns,'t_recv_ns':r}
                        for n,(f,r) in self.ingest.latest.items()}}
                self.marker.content=f'<span id="relay-state" data-capture="{self.fusion.latest_capture}" data-joint="{self.last_joint_ns}" data-y="{float(self.q[1]) if len(self.q) else 0}" data-timing="{html.escape(json.dumps(payload),quote=True)}" style="display:none"></span>'
                self.timing_log.write(json.dumps(payload)+'\n');self.timing_log.flush()
                if self.fusion.cfg.get('record_display_evidence') and self.fusion.publisher and self.mask:
                    self.fusion.publisher.send('fusion/evidence',DisplayEvidence(t_flush,self.flush_seq,points.astype(np.float32),self.mask.states.copy(),coverage.astype(np.float32),unknown,(now-ages.astype(np.float64)*1e9).astype(np.int64)))
        if displayed:self.server.flush()

    def coverage_image(self,name,rgba,shape,w,depth,z):
        visible=self.state_toggles['UNKNOWN'].value
        old=self.coverage_cache.get(name)
        if old is not None and old[1]==visible and np.array_equal(old[0],rgba):return
        self.server.scene.add_image(name,np.flipud(rgba.transpose(1,0,2)),shape[0]*.08,shape[1]*.08,position=(w/2,depth/2,z),visible=visible,cast_shadow=False,receive_shadow=False)
        self.coverage_cache[name]=(rgba.copy(),visible)

    def close(self):
        if self.record_session.process and self.record_session.process.poll() is None:self.stop_recording()
        self.send('stop',{});self.send('shutdown',{});self.ingest.close();self.commands.close();self.ui_control.close();self.fusion.close();self.timing_log.close();self.server.stop()


def main():
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=float,default=0);p.add_argument('--cameras',default='configs/cameras.yaml');p.add_argument('--fusion',default='configs/fusion.yaml');p.add_argument('--cpu-cores',type=int);args=p.parse_args()
    if args.cpu_cores:
        import psutil
        proc=psutil.Process();proc.cpu_affinity(proc.cpu_affinity()[:args.cpu_cores])
    ui=OperatorUI(args.cameras,args.fusion);start=now_ns()
    try:
        while ui.running and (not args.seconds or (now_ns()-start)/1e9<args.seconds):ui.step();time.sleep(.002 if ui.low_latency else .025)
    finally:
        Path('data/logs/ui_latest.json').write_text(json.dumps({'frames':ui.frames,'overflows':ui.ingest.overflows,'elapsed_s':(now_ns()-start)/1e9},indent=2));ui.close()


if __name__=='__main__':main()
