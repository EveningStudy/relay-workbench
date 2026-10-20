"""Capture a 24-second scripted kinematic tour in the procedural operator scene.

Run after scripts/prepare_scene.py, then open localhost:8090 in a browser.
No physics, camera observation, teleoperation or timing claim is made.
"""
from pathlib import Path
import json, os, sys, time
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial.transform import Rotation
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scene_robot'))
os.chdir(ROOT / 'scene_robot')
from p2.ui.operator_ui import OperatorUI


def main():
    ui = OperatorUI()
    ui.header.content = '# Relay\nScripted kinematic preview / procedural scene'
    ui.server.scene.world_axes.visible = False
    print('Open http://127.0.0.1:8090 to start the scene capture.', flush=True)
    deadline = time.monotonic() + 180
    try:
        while not ui.server.get_clients():
            if time.monotonic() > deadline: raise TimeoutError('No browser connected')
            time.sleep(.1)
        time.sleep(3)
        client = next(iter(ui.server.get_clients().values()))
        fps, duration = 8, 24
        frames = []
        font = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 23)
        small = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 16)
        initial = dict(ui.robot_config['initial'])
        for i in range(fps * duration):
            t = i / fps; q = dict(initial)
            q['base_x'] += .12 * np.sin(2*np.pi*t/duration)
            q['base_yaw'] += .18 * np.sin(2*np.pi*t/duration)
            q['lift'] = .15 + .12 * (1-np.cos(2*np.pi*t/duration)) / 2
            q['head_pan'] = .35 * np.sin(2*np.pi*t/12)
            q['head_tilt'] = .35 + .12 * np.sin(2*np.pi*t/12)
            wave = (1-np.cos(2*np.pi*t/12))/2
            q['left_shoulder_pitch'] = -1.0 + .55*wave
            q['left_elbow'] = -.8 - .6*wave
            q['right_shoulder_pitch'] = -1.0 + .55*(1-wave)
            q['right_elbow'] = -.8 - .6*(1-wave)
            ui.robot.update_cfg(q)
            target = np.array([.9, .1, .75])
            angle = -.9 + 2*np.pi*i/(fps*duration)
            position = target + [3.6*np.cos(angle), 3.6*np.sin(angle), 1.65+.2*np.sin(angle)]
            forward = target-position; forward /= np.linalg.norm(forward)
            right = np.cross(forward, [0, 0, 1]); right /= np.linalg.norm(right)
            down = np.cross(forward, right)
            wxyz = Rotation.from_matrix(np.column_stack([right, down, forward])).as_quat(scalar_first=True)
            ui.server.flush()
            rgb = client.get_render(576, 960, position=position, wxyz=wxyz, fov=.82, timeout=30)
            im = Image.fromarray(rgb[:, :, :3]); draw = ImageDraw.Draw(im)
            draw.rectangle((0, 0, 960, 74), fill='#111c25')
            draw.text((24, 12), 'Relay / Procedural robot tour', font=font, fill='white')
            chapter = ['Base + scene overview', 'Lift + stereo head', 'Left arm + wrist camera geometry', 'Right arm + return view'][int(t//6)]
            draw.text((24, 44), f'{chapter}   |   {t:04.1f} / 24 s', font=small, fill='#64cabc')
            draw.rectangle((0, 541, 960, 576), fill='#111c25')
            draw.text((24, 549), 'Scripted kinematics / no physics or live camera feed / no physical robot', font=small, fill='#a8bdc7')
            frames.append(np.asarray(im))
            if i % 32 == 0: print(f'Captured {i+1}/{fps*duration} frames', flush=True)
        out = ROOT / 'docs/media/scene.gif'
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        import subprocess
        process = subprocess.Popen([ff, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pixel_format', 'rgb24',
            '-video_size', '960x576', '-framerate', str(fps), '-i', '-', '-filter_complex',
            '[0:v]fps=6,scale=640:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=none',
            '-loop', '0', str(out)], stdin=subprocess.PIPE)
        for frame in frames: process.stdin.write(frame.tobytes())
        process.stdin.close()
        assert process.wait() == 0
        assert out.stat().st_size < 10_000_000
        print(json.dumps({'rendered_frames': len(frames), 'duration_s': duration, 'gif_fps': 6, 'bytes': out.stat().st_size, 'scripted_kinematics': True, 'physical_robot': False}), flush=True)
    finally:
        ui.close()


if __name__ == '__main__':
    main()
