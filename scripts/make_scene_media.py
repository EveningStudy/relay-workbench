"""Capture a 24-second kitchen tour with recorded joint poses and camera mounts.

Run after scripts/prepare_scene.py, then open localhost:8090 in a browser.
Offline rendering of a fixed scan and historical simulator state; no timing claim.
"""
from pathlib import Path
import json, os, sys, time
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial.transform import Rotation
import imageio_ffmpeg
from kitchen_replay import Replay

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scene_robot'))
os.chdir(ROOT / 'scene_robot')
from p2.ui.operator_ui import OperatorUI
from p2.robot.fk import Kinematics


def camera_views(ui,fk,q,handles):
    names=list(q);values=list(q.values())
    for cam,color in [('head_left',(65,185,255)),('head_right',(110,225,255)),('wrist_left',(255,170,45)),('wrist_right',(255,90,170))]:
        cfg=ui.config['cameras'][cam];pose=fk.pose(cfg['frame'],names,values)
        quat=Rotation.from_matrix(pose[:3,:3]).as_quat(scalar_first=True)
        if cam not in handles:
            if cfg['model']=='kb4':
                segments=[]
                for phi in np.arange(0,2*np.pi,np.pi/4):
                    theta=np.linspace(0,np.pi/2,13)
                    arc=np.c_[np.sin(theta)*np.cos(phi),np.sin(theta)*np.sin(phi),np.cos(theta)]*.28
                    segments.extend(np.stack([arc[:-1],arc[1:]],1))
                theta=np.linspace(0,2*np.pi,33);rim=np.c_[np.cos(theta),np.sin(theta),np.zeros(len(theta))]*.28
                segments.extend(np.stack([rim[:-1],rim[1:]],1))
                handles[cam]=ui.server.scene.add_line_segments('/demo_camera/'+cam,np.asarray(segments),color,thickness=2,thickness_units='screen')
            else:
                fx=cfg['width']/(2*np.tan(np.deg2rad(cfg['horizontal_fov_deg'])/2))
                handles[cam]=ui.server.scene.add_camera_frustum('/demo_camera/'+cam,fov=2*np.arctan(cfg['height']/(2*fx)),aspect=cfg['width']/cfg['height'],scale=.28,color=color)
        handles[cam].position=pose[:3,3];handles[cam].wxyz=quat


def main():
    ui = OperatorUI()
    replay=Replay();fk=Kinematics();handles={}
    ui.header.content = '# Relay\nApproved kitchen scan / recorded simulator joint poses'
    ui.server.scene.world_axes.visible = False
    print('Open http://127.0.0.1:8090 to start the scene capture.', flush=True)
    deadline = time.monotonic() + 180
    try:
        while not ui.server.get_clients():
            if time.monotonic() > deadline: raise TimeoutError('No browser connected')
            time.sleep(.1)
        time.sleep(3)
        client = next(iter(ui.server.get_clients().values()))
        fps, duration = 6, 24
        frames = []
        font = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 23)
        small = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 16)
        for i in range(fps * duration):
            t = i / fps; q = replay.joints(t%12)
            ui.robot.update_cfg(q)
            camera_views(ui,fk,q,handles)
            target = np.array([1.55, .45, .7])
            angle = -.9 + 2*np.pi*i/(fps*duration)
            position = target + [4.0*np.cos(angle), 4.0*np.sin(angle), 1.7+.2*np.sin(angle)]
            forward = target-position; forward /= np.linalg.norm(forward)
            right = np.cross(forward, [0, 0, 1]); right /= np.linalg.norm(right)
            down = np.cross(forward, right)
            wxyz = Rotation.from_matrix(np.column_stack([right, down, forward])).as_quat(scalar_first=True)
            ui.server.flush()
            rgb = client.get_render(576, 960, position=position, wxyz=wxyz, fov=.9, timeout=30)
            im = Image.fromarray(rgb[:, :, :3]); draw = ImageDraw.Draw(im)
            draw.rectangle((0, 0, 960, 74), fill='#111c25')
            draw.text((24, 12), 'Relay / Kitchen scan + robot camera layout', font=font, fill='white')
            chapter = ['216,953 Gaussians / fixed real scan', 'Blue: stereo head / 120-degree pinholes', 'Orange + pink: wrist fisheyes / 180 degrees', 'Recorded simulator poses / orbit return'][int(t//6)]
            draw.text((24, 44), f'{chapter}   |   {t:04.1f} / 24 s', font=small, fill='#64cabc')
            draw.rectangle((0, 541, 960, 576), fill='#111c25')
            draw.text((24, 549), 'Fixed personal scan / historical simulated joint replay / camera outlines / no physical robot', font=small, fill='#a8bdc7')
            frames.append(np.asarray(im))
            if i % 32 == 0: print(f'Captured {i+1}/{fps*duration} frames', flush=True)
        out = ROOT / 'docs/media/scene.gif'
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        import subprocess
        process = subprocess.Popen([ff, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pixel_format', 'rgb24',
            '-video_size', '960x576', '-framerate', str(fps), '-i', '-', '-filter_complex',
            '[0:v]fps=6,scale=720:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=none',
            '-loop', '0', str(out)], stdin=subprocess.PIPE)
        for frame in frames: process.stdin.write(frame.tobytes())
        process.stdin.close()
        assert process.wait() == 0
        assert out.stat().st_size < 10_000_000
        print(json.dumps({'rendered_frames': len(frames), 'duration_s': duration, 'gif_fps': 6, 'bytes': out.stat().st_size, 'historical_simulator_joint_replay': True, 'physical_robot': False}), flush=True)
    finally:
        ui.close();replay.close()


if __name__ == '__main__':
    main()
