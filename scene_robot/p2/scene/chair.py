"""Versioned procedural chair primitives shared by simulation and evaluation.

Old episode scene snapshots lack a chair entry and retain the exact two-part
historical asset. New dimensions are authored procedural geometry, not a scan.
"""


def chair_boxes(scene):
    cy=-1.4 if scene['desk'].get('solid_block') else .9
    cfg=scene.get('chair')
    if cfg is None:
        return [('seat',[1.7,cy,.45],[.42,.4,.06]),('back',[1.7,cy+.18,.7],[.42,.06,.5])]
    if cfg['version']!='four_leg_v1':raise ValueError('Unknown procedural chair version')
    x,y=cfg['origin_xy'];width,depth=cfg['seat_size_xy'];top=cfg['seat_top_m']
    thick=cfg['seat_thickness_m'];leg=cfg['leg_width_m'];back=cfg['back_thickness_m'];height=cfg['back_top_m']
    if not (width>2*leg and depth>2*leg and top>thick>0 and height>top and back>0):
        raise ValueError('Invalid chair dimensions')
    boxes=[('seat',[x,y,top-thick/2],[width,depth,thick]),
           ('back',[x,y+depth/2-back/2,(top+height)/2],[width,back,height-top])]
    for ix,dx in enumerate([-1,1]):
        for iy,dy in enumerate([-1,1]):
            boxes.append((f'leg_{ix}_{iy}',[x+dx*(width/2-leg),y+dy*(depth/2-leg),(top-thick)/2],
                          [leg,leg,top-thick]))
    return boxes
