"""Procedural asset versioning must preserve old episode reference geometry."""
import numpy as np
from p2.scene.chair import chair_boxes


def test_historical_chair_and_four_grounded_legs():
    old={'desk':{'solid_block':True}}
    assert chair_boxes(old)==[('seat',[1.7,-1.4,.45],[.42,.4,.06]),('back',[1.7,-1.4+.18,.7],[.42,.06,.5])]
    new={**old,'chair':dict(version='four_leg_v1',origin_xy=[1.7,-1.4],seat_size_xy=[.42,.4],
                          seat_top_m=.48,seat_thickness_m=.06,leg_width_m=.035,back_top_m=.95,back_thickness_m=.06)}
    parts=chair_boxes(new);assert len(parts)==6
    legs=[(np.array(center),np.array(size)) for name,center,size in parts if name.startswith('leg_')]
    assert len(legs)==4 and len({tuple(center[:2]) for center,size in legs})==4
    for center,size in legs:
        assert np.isclose(center[2]-size[2]/2,0)
        assert np.isclose(center[2]+size[2]/2,.42)
