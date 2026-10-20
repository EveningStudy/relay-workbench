"""Real-time SAPIEN node with independent exposure and delayed delivery queues."""
import argparse
import heapq
import json
from pathlib import Path
import time
import numpy as np
import sapien
import yaml
import cv2
from p2.bus import Publisher, Subscriber, COMMANDS
from p2.clock import now_ns
from p2.msgs import CameraFrame, JointState, Odom, Status, Command
from p2.sim.scenario import Scenario
from p2.sim.robot import Robot
from p2.sim.sensors import Sensor
from p2.scene.build_sim_scene import build_world


def run(args):
    cv2.setNumThreads(1)
    cfg=yaml.safe_load(Path(args.cameras).read_text())
    sapien.render.set_camera_shader_dir(cfg.get('render_shader','minimal'))
    sapien.render.set_picture_format('Color','r8g8b8a8unorm')
    sapien.render.set_picture_format('ColorRaw','r8g8b8a8unorm')
    sapien.render.set_picture_format('PositionSegmentation','r16g16b16a16sint')
    scene=sapien.Scene();scene.set_timestep(1/120);scene.add_ground(0)
    scene.set_ambient_light([0.45]*3);scene.add_directional_light([1,1,-2],[1.5]*3)
    robot=Robot(scene)
    actors=build_world(scene) if Path('assets/scan/old_map.ply').exists() else {}
    sensors={n:Sensor(scene,robot,n,c) for n,c in cfg['cameras'].items()}
    scenario=Scenario(args.scenario,actors,cfg['cameras'])
    external=scene.add_camera('external',640,400,1.0,.03,8.)
    from scipy.spatial.transform import Rotation
    scene_cfg=yaml.safe_load(Path('configs/scene.yaml').read_text())
    width=scene_cfg['desk']['width_x'];eye=np.array([width+.8,-2.1,2.6]);forward=np.array([width/2,.5,.7])-eye;forward/=np.linalg.norm(forward)
    left=np.cross([0,0,1],forward);left/=np.linalg.norm(left);up=np.cross(forward,left)
    external.entity.pose=sapien.Pose(eye,Rotation.from_matrix(np.stack([forward,left,up],1)).as_quat()[[3,0,1,2]])
    pub=Publisher();commands=Subscriber('',COMMANDS)
    rng=np.random.default_rng(cfg['seed']);start=now_ns();last_tick=start;last_state=0;last_command=0
    next_capture={n:start for n in sensors};pending=[];order=0;counts={n:0 for n in sensors};drops={n:0 for n in sensors};seq={n:0 for n in sensors}
    timings={n:[] for n in sensors};physics_times=[];last_external=0;external_seq=0;last_action=0;last_truth=0
    def deliver():
        while pending and pending[0][0]<=now_ns():
            _,_,frame=heapq.heappop(pending);frame.t_send_ns=now_ns();pub.send('camera/'+frame.cam_id,frame);counts[frame.cam_id]+=1
    print('SIM READY',flush=True);running=True
    try:
        while running and ((now_ns()-start)/1e9<args.seconds or not args.seconds):
            now=now_ns();elapsed=(now-start)/1e9
            msg=commands.recv(0)
            while msg:
                command=msg[1];last_command=now_ns()
                if command.action=='stop': robot.velocity[:]=0;robot.targets=robot.body.get_qpos().copy()
                elif command.action=='shutdown':running=False
                elif command.action=='velocity': robot.velocity=np.asarray(command.values['velocity'])
                elif command.action=='joints':
                    for n,v in command.values.items(): robot.set_target(n,v)
                msg=commands.recv(0)
            allow=now-last_command>250_000_000
            if allow:robot.velocity[:]=0
            scenario.update(elapsed,robot,allow)
            if allow and now-last_action>100_000_000:
                pub.send('action/script',Command(now,'velocity',{'velocity':robot.velocity.tolist()}))
                pub.send('action/script',Command(now,'joints',dict(zip(robot.names,robot.targets.tolist()))));last_action=now
            physics_start=now_ns()
            while now-last_tick>=int(1e9/120):
                robot.step();scene.step();last_tick+=int(1e9/120)
                names,q=robot.state()
                pub.send('state/joints',JointState(last_tick,names,q))
                odom=np.array([q[names.index(n)] for n in ['base_x','base_y','base_yaw']])+rng.normal(0,cfg['odom_noise_m'],3)
                pub.send('state/odom',Odom(last_tick,odom));last_state=last_tick
            physics_times.append((now_ns()-physics_start)/1e6)
            pair_time=None
            for n,sensor in sensors.items():
                if cfg.get('low_latency'):deliver()
                c=cfg['cameras'][n]
                if n=='head_right' and pair_time is None:continue
                if n!='head_right' and now_ns()<next_capture[n]: continue
                next_capture[n]+=int(1e9/c['hz']+rng.uniform(-1,1)*c['exposure_jitter_ms']*1e6)
                if next_capture[n]<now_ns():
                    period=int(1e9/c['hz'])
                    next_capture[n]+=((now_ns()-next_capture[n])//period+1)*period
                seq[n]+=1
                if n=='head_left':pair_time=now_ns()
                if n=='head_right':seq[n]=seq['head_left']
                if any(a<=elapsed<=b for a,b in c['outages']) or rng.random()<c['drop_probability']:
                    drops[n]+=1;continue
                # Physics is held constant during synchronous rendering; capture state is timestamped here.
                t=now_ns();names,q=robot.state();pub.send('state/joints',JointState(t,names,q))
                if n=='head_left':pair_time=t
                capture_t=(pair_time+int(rng.uniform(-1,1)*c['exposure_jitter_ms']*1e6)) if n.startswith('head_') else t
                rgb,depth=sensor.capture();render_done=now_ns();timings[n].append((render_done-t)/1e6)
                if n=='head_left' and t-last_truth>200_000_000:
                    pub.send('gt/depth',CameraFrame(n,seq[n],capture_t,now_ns(),'synthetic',c['model'],c['width'],c['height'],rgb,depth,'evaluation_only'))
                    pub.send('gt/poses',Status(t,{'objects':{k:a.pose.to_transformation_matrix().tolist() for k,a in actors.items()},'cameras':{k:s.link.pose.to_transformation_matrix().tolist() for k,s in sensors.items()}}));last_truth=t
                if cfg.get('eval_truth_all') and (not timings[n] or seq[n]%max(1,round(c['hz']/5))==0):
                    pub.send('gt/depth',CameraFrame(n,seq[n],capture_t,now_ns(),'synthetic',c['model'],c['width'],c['height'],rgb,depth,'evaluation_only'))
                if c.get('noise_sigma_z2'):
                    depth=np.maximum(0,depth+rng.normal(size=depth.shape).astype(np.float32)*c['noise_sigma_z2']*depth**2)
                frame=CameraFrame(n,seq[n],capture_t+int(c['timestamp_bias_ms']*1e6),0,'synthetic',c['model'],c['width'],c['height'],rgb,depth if c['depth_mode']=='sim_ideal' else None,'sim_ideal' if c['depth_mode']=='sim_ideal' else 'none')
                frame.timing={'t_render_ns':render_done}
                delay=max(0,rng.normal(c['delay_ms'],c['jitter_ms']))
                order+=1;heapq.heappush(pending,(now_ns()+int(delay*1e6),order,frame))
            while pending and pending[0][0]<=now_ns():
                _,_,frame=heapq.heappop(pending);frame.t_send_ns=now_ns();pub.send('camera/'+frame.cam_id,frame);counts[frame.cam_id]+=1
            if cfg.get('external_hz',15)>0 and now_ns()-last_external>=int(1e9/cfg.get('external_hz',15)):
                last_external=now_ns();scene.update_render();external.take_picture();external_seq+=1
                pub.send('video/external',CameraFrame('external',external_seq,last_external,now_ns(),'synthetic','pinhole',640,400,external.get_picture('Color')[...,:3].copy(),None,'none'))
            if now-last_state>1e9: time.sleep(0.001)
            time.sleep(0.0005)
    finally:
        time.sleep(.2);pub.send('status/sim',Status(now_ns(),{'counts':counts,'drops':drops,'end':True}));time.sleep(.2)
        result={'elapsed_s':(now_ns()-start)/1e9,'counts':counts,'drops':drops,'capture_median_ms':{n:float(np.median(t)) if t else 0 for n,t in timings.items()},'physics_loop_median_ms':float(np.median(physics_times)),'source':'synthetic','scene':scene_cfg['label'],'pid':__import__('os').getpid()}
        Path('data/logs/sim_latest.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
        pub.close();commands.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=float,default=0);p.add_argument('--cameras',default='configs/cameras.yaml');p.add_argument('--scenario',default='empty');args=p.parse_args();run(args)


if __name__=='__main__': main()
