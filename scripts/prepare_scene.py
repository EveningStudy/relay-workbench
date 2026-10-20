"""Restore the approved kitchen prior and generate the robot geometry."""
from pathlib import Path
import os, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scene_robot'))

def prepare():
    import numpy as np
    from plyfile import PlyData, PlyElement
    from PIL import Image
    from p2.robot.gen_robot import generate
    os.chdir(ROOT/'scene_robot')
    Path('assets/scan').mkdir(parents=True,exist_ok=True)
    Path('data/logs').mkdir(parents=True,exist_ok=True)
    generate()
    with np.load('assets/kitchen/prior.npz',allow_pickle=False) as packed:
        vertices=packed['vertex']
    PlyData([PlyElement.describe(vertices,'vertex')],text=False).write('assets/scan/old_map.ply')
    Image.open('assets/kitchen/tabletop.png').convert('RGB').save('assets/scan/real_desktop_texture.png')
    print(f'Restored {len(vertices)} approved kitchen Gaussians and generated robot geometry.')

if __name__=='__main__':prepare()
