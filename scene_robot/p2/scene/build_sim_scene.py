"""Procedural placeholder and scan-based simulator scene construction."""
import argparse
from pathlib import Path
import json
import numpy as np
import trimesh
import yaml


def meshes(cfg):
    result=[]
    def box(name,size,position,color):
        mesh=trimesh.creation.box(size);mesh.apply_translation(position)
        mesh.visual.vertex_colors=np.tile(np.r_[np.asarray(color)*255,255].astype(np.uint8),(len(mesh.vertices),1))
        result.append((name,mesh,np.array(color)))
    d=cfg['desk'];w,h=d['width_x'],d['height_z'];dep=d['depth_y'];th=d['top_thickness']
    box('floor',[w+2,dep+2,.03],[w/2,dep/2,-.015],[.35,.38,.4])
    if d.get('solid_block'):
        box('desktop',[w,dep,h],[w/2,dep/2,h/2],[.65,.65,.62])
    else:
        box('backdrop',[2.4,.04,1.8],[.6,1.2,.9],[.38,.41,.45])
        box('desktop',[w,dep,th],[w/2,dep/2,h-th/2],[.52,.38,.23])
        for x in [.05,w-.05]:
            for y in [.05,dep-.05]:box(f'leg_{x}_{y}',[.05,.05,h-th],[x,y,(h-th)/2],[.2,.23,.25])
    for name,o in cfg['objects'].items():
        if name=='mug':
            radius=o['size'][0]/2;height=o['size'][2]
            body=trimesh.creation.annulus(r_min=radius*.75,r_max=radius,height=height,sections=24)
            if d.get('solid_block'):
                handle=trimesh.creation.annulus(r_min=.018,r_max=.025,height=.012,sections=24)
                handle.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,[1,0,0]));handle.apply_translation([radius,0,0])
                mesh=trimesh.util.concatenate([body,handle]);mesh.apply_transform(trimesh.transformations.rotation_matrix(np.deg2rad(o.get('yaw_deg',0)),[0,0,1]))
            else:mesh=body
            mesh.apply_translation(o['position']);result.append((name,mesh,np.array(o['color'])))
        else:box(name,o['size'],o['position'],o['color'])
    return result


def build_world(scene,config='configs/scene.yaml'):
    import sapien
    cfg=yaml.safe_load(Path(config).read_text());actors={}
    for name,mesh,color in meshes(cfg):
        if name=='floor':continue
        path=Path('assets/scan')/(name+'.obj');mesh.export(path)
        builder=scene.create_actor_builder();builder.add_visual_from_file(str(path),material=sapien.render.RenderMaterial(base_color=[*color,1]))
        if name=='desktop':
            from p2.scene.texture import add_surface
            add_surface(builder,cfg['desk'])
        if name=='backdrop':
            from p2.scene.texture import add_wall
            add_wall(builder)
        bounds=mesh.bounds;size=(bounds[1]-bounds[0])/2;center=mesh.centroid
        if name in cfg['objects']:
            # Mesh vertices carry original scan/world placement; actor transform starts at identity.
            builder.add_convex_collision_from_file(str(path))
            actor=builder.build_kinematic(name)
        else:
            builder.add_box_collision(pose=sapien.Pose(center),half_size=size)
            actor=builder.build_static(name)
        actors[name]=actor
    # Procedural chair remains outside the original scan and is moved by scenarios.
    builder=scene.create_actor_builder()
    from p2.scene.chair import chair_boxes
    for part,center,size in chair_boxes(cfg):
        builder.add_box_visual(pose=sapien.Pose(center),half_size=np.array(size)/2,material=[.12,.15,.18])
        builder.add_box_collision(pose=sapien.Pose(center),half_size=np.array(size)/2)
    actors['chair']=builder.build_kinematic('chair')
    builder=scene.create_actor_builder()
    builder.add_visual_from_file('assets/scan/mug.obj',material=sapien.render.RenderMaterial(base_color=[.8,.2,.2,1]))
    builder.add_convex_collision_from_file('assets/scan/mug.obj')
    actors['new_mug']=builder.build_kinematic('new_mug')
    actors['new_mug'].pose=sapien.Pose([0,0,-3])
    return actors


def main():
    p=argparse.ArgumentParser();p.add_argument('--placeholder',action='store_true');args=p.parse_args()
    cfg=yaml.safe_load(Path('configs/scene.yaml').read_text());items=meshes(cfg)
    if args.placeholder and cfg['desk'].get('solid_block'):raise ValueError('Refusing to overwrite real scene with placeholder')
    combined=trimesh.util.concatenate([m for _,m,_ in items]);target='placeholder_world.obj' if args.placeholder else 'aligned_mesh.obj';combined.export(Path('assets/scan')/target)
    Path('assets/scan/scene_parts.json').write_text(json.dumps({name:{'bounds':m.bounds.tolist(),'color':c.tolist()} for name,m,c in items},indent=2))
    print(cfg['label'],target)


if __name__=='__main__':main()
