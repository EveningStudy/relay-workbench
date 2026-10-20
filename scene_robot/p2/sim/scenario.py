"""Config-driven physics events and honestly labelled scripted trajectories."""
from pathlib import Path
import numpy as np
import sapien
import yaml


class Scenario:
    def __init__(self,name,actors,cameras):
        path=Path(name)
        if not path.exists():path=Path('configs/scenarios')/(name+'.yaml')
        self.cfg=yaml.safe_load(path.read_text()) if path.exists() else {'name':'empty','duration':0,'events':[],'trajectory':{}}
        self.actors=actors;self.cameras=cameras;self.done=set()
        self.original={n:dict(c) for n,c in cameras.items()}

    def update(self,t,robot,allow_trajectory=True):
        tr=self.cfg.get('trajectory',{})
        # Scripted, config-visible viewing dwell; never a human trajectory.
        for phase in self.cfg.get('viewing_phases',[]):
            if t>=phase['at']:
                tr={**tr,**phase.get('trajectory',{}),
                    'joints':{**tr.get('joints',{}),**phase.get('trajectory',{}).get('joints',{})}}
        if tr and allow_trajectory:
            velocity=np.array(tr.get('velocity',[0,0,0]),float)
            for i,key in enumerate(['vx','vy','yaw']):
                if key in tr:velocity[i]+=tr[key].get('amplitude',0)*np.sin(t*tr[key].get('omega',1))
            robot.velocity=velocity
            for name,value in tr.get('joints',{}).items():
                if isinstance(value,dict):value=value.get('center',0)+value.get('amplitude',0)*np.sin(t*value.get('omega',1))
                robot.set_target(name,value)
        for index,event in enumerate(self.cfg.get('events',[])):
            at=event['at'];duration=event.get('duration',0)
            if event['action']=='camera':
                active=at<=t<at+duration
                cam=self.cameras[event['camera']]
                for key,value in event['set'].items():cam[key]=value if active else self.original[event['camera']].get(key,value)
                continue
            if t<at:continue
            if event['action']=='path':
                alpha=np.clip((t-at)/duration,0,1)
                xyz=np.array(event.get('from',[0,0,0]))*(1-alpha)+np.array(event['to'])*alpha
                self.actors[event['actor']].pose=sapien.Pose(xyz)
            elif index not in self.done:
                self.actors[event['actor']].pose=sapien.Pose(event['translation']);self.done.add(index)


def load_config(name):
    return Scenario(name,{},{}).cfg
