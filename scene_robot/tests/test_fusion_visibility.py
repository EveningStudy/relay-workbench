from pathlib import Path
import numpy as np
import yaml
from p2.fusion.voxel_map import VoxelMap
from p2.fusion.tf_buffer import TransformBuffer
from p2.msgs import JointState,Odom


def test_ray_does_not_carve_behind_hit():
    cfg=yaml.safe_load(Path('configs/fusion.yaml').read_text());cfg['device']='cpu'
    m=VoxelMap(cfg);m.integrate([0,0,.5],[[.5,0,.5]],[[200,0,0]],123)
    idx,valid=m.index(__import__('torch').tensor([[.3,0,.5],[.5,0,.5],[.8,0,.5]]))
    v=m.logodds[idx].numpy()
    assert v[0]<0 and v[1]>0 and v[2]==0


def test_odometry_overrides_virtual_base_state():
    tf=TransformBuffer();names=['base_x','base_y','base_yaw']
    tf.add(JointState(100,names,np.array([99.,99.,0.])))
    tf.add(Odom(100,np.array([.1,.2,0.])))
    pose,_=tf.pose('base',100)
    assert np.allclose(pose[:2,3],[.1,.2])
