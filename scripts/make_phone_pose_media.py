"""Render synchronized approved phone RGB and its estimated pose in the kitchen."""
import json,os,sys,time,subprocess
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from scipy.spatial.transform import Rotation
import imageio_ffmpeg
from phone_replay import ROOT,CAMERA,TRACK,images
from make_camera_media import encode

sys.path.insert(0,str(ROOT/'scene_robot'))
from p2.ui.operator_ui import OperatorUI

def main():
    os.chdir(ROOT/'scene_robot')
    cfg=json.loads(CAMERA.read_text());track=json.loads(TRACK.read_text())
    k=np.asarray(cfg['camera_matrix']);d=np.asarray(cfg['distortion'])
    frames=[cv2.undistort(rgb,k,d) for rgb in images()]
    ui=OperatorUI();ui.header.content='# Relay\nPhone RGB and checkerboard-derived camera pose'
    ui.server.scene.world_axes.visible=False
    ui.server.scene.add_point_cloud('/phone_board',np.asarray(cfg['board_world_points']),colors=(60,210,180),point_size=.007)
    frustum=ui.server.scene.add_camera_frustum('/phone_pose',fov=2*np.arctan(540/(2*k[1,1])),
        aspect=960/540,scale=.32,color=(30,210,230),visible=False)
    axes=ui.server.scene.add_frame('/phone_pose_axes',axes_length=.16,axes_radius=.004,visible=False)
    history=[];segments=[];previous=None;last_valid=None
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',20)
    small=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',17)
    bold=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',27)
    out=ROOT/'outputs/phone_pose_render';out.mkdir(parents=True,exist_ok=True)
    print('Open http://127.0.0.1:8090 for the phone-pose capture.',flush=True)
    try:
        deadline=time.monotonic()+180
        while not ui.server.get_clients():
            if time.monotonic()>deadline:raise TimeoutError('No browser connected')
            time.sleep(.1)
        time.sleep(2);client=next(iter(ui.server.get_clients().values()))
        target=np.array([1.15,.45,.85]);position=np.array([-2.7,-3.3,2.8])
        forward=target-position;forward/=np.linalg.norm(forward)
        right=np.cross(forward,[0,0,1]);right/=np.linalg.norm(right);down=np.cross(forward,right)
        viewquat=Rotation.from_matrix(np.column_stack([right,down,forward])).as_quat(scalar_first=True)
        output=[]
        for row,rgb in zip(track['frames'],frames):
            pose=row['pose'];valid=pose is not None
            frustum.visible=axes.visible=valid
            if valid:
                t=np.asarray(pose['T_world_camera']);p=t[:3,3];q=Rotation.from_matrix(t[:3,:3]).as_quat(scalar_first=True)
                frustum.position=axes.position=p;frustum.wxyz=axes.wxyz=q;frustum.image=rgb
                history.append(p.copy());last_valid=row['original_t_s']
                if previous is not None:segments.append([previous,p.copy()])
                previous=p.copy()
                ui.server.scene.add_point_cloud('/phone_history',np.asarray(history),colors=(30,210,230),point_size=.014)
                if segments:ui.server.scene.add_line_segments('/phone_trail',np.asarray(segments),colors=(30,210,230),thickness=2,thickness_units='screen')
            else:previous=None
            ui.server.flush()
            rendered=client.get_render(480,720,position=position,wxyz=viewquat,fov=.85,timeout=30)
            canvas=Image.new('RGB',(1280,648),'#101c26');draw=ImageDraw.Draw(canvas)
            draw.text((24,12),'Relay / Phone video -> camera pose in the kitchen',font=bold,fill='#edf4f7')
            draw.text((24,49),f"Source {row['original_t_s']:05.2f}s / approved 6-18s / known checkerboard placement / RGB only",font=small,fill='#a8becb')
            canvas.paste(Image.fromarray(rgb).resize((512,288)),(24,116))
            # Fixed crop keeps the phone, board and robot legible in the README.
            view=Image.fromarray(rendered[:,:,:3]).crop((150,110,600,410)).resize((720,480))
            canvas.paste(view,(552,116))
            draw.text((24,86),'Phone recording / undistorted RGB',font=font,fill='#a8becb')
            draw.text((552,86),'Operator scene / estimated camera frustum + history',font=font,fill='#a8becb')
            color='#69d2c3' if valid else '#f2b66c'
            draw.text((24,426),'POSE VALID' if valid else 'POSE UNAVAILABLE / frustum hidden',font=font,fill=color)
            if valid:
                draw.text((24,461),f'Position: x {p[0]:+.3f}  y {p[1]:+.3f}  z {p[2]:+.3f} m',font=small,fill='#edf4f7')
                draw.text((24,491),f"Board reprojection RMS: {pose['rms_px']:.3f} px",font=small,fill='#a8becb')
            else:
                reason=row['reason'].replace('_',' ')
                draw.text((24,461),reason,font=small,fill='#a8becb')
                draw.text((24,491),f'Last valid: {last_valid:.2f}s / no pose interpolation' if last_valid is not None else 'No valid pose yet / no interpolation',font=small,fill='#a8becb')
            draw.text((24,533),f"{track['valid']}/72 sampled frames have a pose",font=small,fill='#a8becb')
            draw.text((24,563),'Track gaps retained / cyan trail = valid history',font=small,fill='#a8becb')
            draw.rectangle((0,610,1280,648),fill='#0b141c')
            draw.text((24,620),'Offline image-derived pose / fixed kitchen scan / no physical robot, real depth fusion or new timing result',font=small,fill='#a8becb')
            canvas.save(out/f'{row["seq"]:03}.png');output.append(canvas)
            if row['seq']%12==0:print(f"Rendered {row['seq']}/72",flush=True)
        dest=ROOT/'docs/media';encode(output,dest/'phone.gif',width=960)
        ff=imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run([ff,'-y','-v','error','-framerate','6','-i',str(out/'%03d.png'),'-an','-map_metadata','-1',
            '-vf','scale=960:-2','-c:v','libx264','-crf','23','-pix_fmt','yuv420p',str(dest/'phone_pose.mp4')],check=True)
        print(json.dumps({'frames':72,'duration_s':12,'valid':track['valid'],'gif_bytes':(dest/'phone.gif').stat().st_size,'mp4_bytes':(dest/'phone_pose.mp4').stat().st_size}),flush=True)
    finally:ui.close()

if __name__=='__main__':main()
