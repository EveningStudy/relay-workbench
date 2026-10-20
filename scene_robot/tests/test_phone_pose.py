"""Regress image/world handedness and the iPad outer-to-inner corner offset."""
import cv2,numpy as np
from p2.io.phone_pose import board_points,estimate


def test_above_desk_pose_from_rendered_board(tmp_path,monkeypatch):
    # This is an explicitly synthetic unit fixture, never a human-camera result.
    monkeypatch.chdir(tmp_path);folder=tmp_path/'human_inputs';(folder/'04_phone_calibration').mkdir(parents=True)
    (folder/'04_phone_calibration/board.txt').write_text('17 mm')
    (folder/'02_measurements.yaml').write_text('desk: {height_z: 0.9}\ncalibration_board: {square_size_m: 0.017, near_left_corner_xy: [0.16, 0.08], height_above_desk_m: 0.0061}\n')
    p=board_points();s=.017;z=p[0,2];origin=p[0,:2]-s
    assert np.allclose(p[0],[.177,.097,.9061])
    outer=np.array([[*origin,z],[origin[0]+11*s,origin[1],z],[origin[0]+11*s,origin[1]+8*s,z],[origin[0],origin[1]+8*s,z]],np.float32)
    k=np.array([[800.,0,640],[0,800,360],[0,0,1]]);r=np.diag([1.,-1.,-1.]);center=np.array([.25,.15,1.5]);rv=cv2.Rodrigues(r)[0];tv=-r@center
    uv=cv2.projectPoints(outer,rv,tv,k,np.zeros(5))[0].reshape(-1,2)
    pattern=np.zeros((8*64,11*64),np.uint8)
    for y in range(8):
        for x in range(11):pattern[y*64:(y+1)*64,x*64:(x+1)*64]=255 if (x+y)%2 else 0
    h=cv2.getPerspectiveTransform(np.array([[0,0],[704,0],[704,512],[0,512]],np.float32),uv.astype(np.float32));gray=cv2.warpPerspective(pattern,h,(1280,720),borderValue=150)
    pose,reason=estimate(gray,k,np.zeros(5));assert pose is not None,reason
    actual=np.array(pose['T_world_camera']);assert np.linalg.norm(actual[:3,3]-center)<.015
    assert np.linalg.norm(actual[:3,:3]-r.T)<.05
