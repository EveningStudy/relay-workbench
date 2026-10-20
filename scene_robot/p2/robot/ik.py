"""Damped least-squares end-effector translation from URDF FK."""
import numpy as np
from p2.robot.fk import Kinematics


def nudge(names,q,side,delta):
    kin=Kinematics();q=np.asarray(q,dtype=float).copy();frame=f"{side}_palm"
    indices=[i for i,n in enumerate(names) if n.startswith(side+"_") and 'finger' not in n]
    p=kin.pose(frame,names,q)[:3,3];jac=[]
    for i in indices:
        qq=q.copy();qq[i]+=1e-4
        jac.append((kin.pose(frame,names,qq)[:3,3]-p)/1e-4)
    j=np.array(jac).T
    step=j.T@np.linalg.solve(j@j.T+np.eye(3)*0.02**2,np.asarray(delta))
    for i,d in zip(indices,step): q[i]+=np.clip(d,-0.1,0.1)
    return dict(zip(names,q.tolist()))
