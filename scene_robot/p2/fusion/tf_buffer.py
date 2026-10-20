"""Timestamped robot state interpolation with URDF FK and observed odometry."""
from collections import deque
import numpy as np
from p2.msgs import JointState, Odom
from p2.robot.fk import Kinematics


class TransformBuffer:
    def __init__(self,max_age_ms=500):
        self.joints=deque(maxlen=2400);self.odom=deque(maxlen=2400);self.kin=Kinematics();self.max_gap_ns=int(max_age_ms*1e6)

    def add(self,message):
        if isinstance(message,JointState):self.joints.append(message)
        elif isinstance(message,Odom):self.odom.append(message)

    def _interp(self,items,t,attr):
        if not items:raise LookupError('no state')
        times=np.array([x.t_ns for x in items],np.int64)
        i=int(np.searchsorted(times,t));a=items[max(0,i-1)];b=items[min(i,len(items)-1)]
        gap=min(abs(t-a.t_ns),abs(t-b.t_ns))
        if gap>self.max_gap_ns:raise LookupError('pose unavailable')
        alpha=np.clip((t-a.t_ns)/max(1,b.t_ns-a.t_ns),0,1)
        qa=np.asarray(getattr(a,attr));qb=np.asarray(getattr(b,attr))
        return qa+(qb-qa)*alpha,gap

    def pose(self,frame,t,uncertainty_ms=2):
        q,gap=self._interp(self.joints,t,'q');odom,ogap=self._interp(self.odom,t,'pose');names=self.joints[-1].names
        q=q.copy()
        for n,v in zip(['base_x','base_y','base_yaw'],odom):
            if n in names:q[names.index(n)]=v
        pose=self.kin.pose(frame,names,q)
        speed=0.;angular=0.
        if len(self.joints)>1:
            dt=max((self.joints[-1].t_ns-self.joints[-2].t_ns)/1e9,1e-6)
            dq=(self.joints[-1].q-self.joints[-2].q)/dt
            speed=float(np.linalg.norm(dq[:2]));angular=float(np.linalg.norm(dq[2:]))
        sigma=(uncertainty_ms*1e6+max(gap,ogap))/1e9
        return pose,{'linear_m':speed*sigma,'angular_rad':angular*sigma,'timestamp_sigma_ms':sigma*1000}
