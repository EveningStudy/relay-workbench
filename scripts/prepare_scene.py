"""Generate a public procedural prior; never loads a personal scan."""
from pathlib import Path
import os, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scene_robot'))

def prepare():
    import numpy as np
    import yaml, trimesh
    from p2.robot.gen_robot import generate
    from p2.scene.build_sim_scene import meshes
    from p2.scene.load_splat import save
    from p2.scene.texture import make
    os.chdir(ROOT/'scene_robot')
    Path('assets/scan').mkdir(parents=True,exist_ok=True)
    Path('data/logs').mkdir(parents=True,exist_ok=True)
    generate()
    cfg=yaml.safe_load(Path('configs/scene.yaml').read_text())
    items=meshes(cfg);rng=np.random.default_rng(7)
    points=[];colors=[];area=sum(m.area for _,m,_ in items)
    for _,mesh,color in items:
        p,_=trimesh.sample.sample_surface(mesh,max(1,round(cfg['gaussian_count']*mesh.area/area)),seed=rng)
        points.append(p);colors.append(np.tile(color,(len(p),1)))
    make()
    save('assets/scan/old_map.ply',np.concatenate(points),np.concatenate(colors),scale=.012)
    print(f'Generated {sum(map(len,points))} procedural Gaussians and robot geometry; no personal assets.')

if __name__=='__main__':prepare()
