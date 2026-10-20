"""Deterministic procedural desk texture; no downloaded images."""
from pathlib import Path
import numpy as np
from PIL import Image


def make():
    rng=np.random.default_rng(17)
    tex=rng.integers(70,220,(64,128,3),dtype=np.uint8)
    tex=np.repeat(np.repeat(tex,4,axis=0),4,axis=1)
    path=Path('assets/scan/desktop_texture.png');Image.fromarray(tex).save(path)
    return tex


def add_surface(builder,desk):
    import sapien
    real=desk.get('solid_block',False)
    if not real:make()
    w,d,h=desk['width_x'],desk['depth_y'],desk['height_z']+.0005
    obj=Path('assets/scan/desktop_surface.obj')
    obj.write_text(f'v 0 0 {h}\nv {w} 0 {h}\nv {w} {d} {h}\nv 0 {d} {h}\nvt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\nf 1/1 2/2 3/3\nf 1/1 3/3 4/4\n')
    mat=sapien.render.RenderMaterial(base_color=[1,1,1,1]);mat.base_color_texture=sapien.render.RenderTexture2D('assets/scan/real_desktop_texture.png' if real else 'assets/scan/desktop_texture.png')
    builder.add_visual_from_file(str(obj),material=mat)


def add_wall(builder):
    import sapien
    make();obj=Path('assets/scan/backdrop_surface.obj')
    obj.write_text('v -0.6 1.1795 0\nv 1.8 1.1795 0\nv 1.8 1.1795 1.8\nv -0.6 1.1795 1.8\nvt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\nf 1/1 2/2 3/3\nf 1/1 3/3 4/4\n')
    mat=sapien.render.RenderMaterial(base_color=[1,1,1,1]);mat.base_color_texture=sapien.render.RenderTexture2D('assets/scan/desktop_texture.png')
    builder.add_visual_from_file(str(obj),material=mat)
