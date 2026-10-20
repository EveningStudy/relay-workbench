"""Build camera GIFs from the bundled, timestamped simulator RGB excerpt."""
from pathlib import Path
import subprocess,json
import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageOps
import imageio_ffmpeg
from kitchen_replay import Replay,ROOT

BG='#101c26';TEAL='#69d2c3';WHITE='#edf4f7';MUTED='#a8becb'
FONT=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',18)
BOLD=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',26)

def encode(frames,path,fps=6,width=720):
    w,h=frames[0].size
    process=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-f','rawvideo',
        '-pixel_format','rgb24','-video_size',f'{w}x{h}','-framerate',str(fps),'-i','-',
        '-filter_complex',f'[0:v]scale={width}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=none',
        '-loop','0',str(path)],stdin=subprocess.PIPE)
    for frame in frames:process.stdin.write(np.asarray(frame).tobytes())
    process.stdin.close()
    if process.wait():raise RuntimeError('GIF encoding failed')
    if path.stat().st_size>=10_000_000:raise ValueError('GIF exceeds 10 MB')

def panel(im,replay,cam,t,rect,label):
    x,y,w,h=rect;draw=ImageDraw.Draw(im)
    draw.rounded_rectangle((x,y,x+w,y+h),radius=10,fill='#172936')
    draw.text((x+14,y+10),label,font=FONT,fill=TEAL)
    row=replay.latest(cam,t)
    if row:
        source=replay.image(row);view=ImageOps.contain(source,(w-20,h-76))
        im.paste(view,(x+(w-view.width)//2,y+40+(h-76-view.height)//2))
        draw.text((x+14,y+h-27),f"Recorded exposure {row['capture_ns']/1e9:05.2f}s / frame {row['seq']}",font=FONT,fill=MUTED)
    else:draw.text((x+24,y+70),'Waiting for first recorded delivery',font=FONT,fill=MUTED)

def main():
    replay=Replay();gallery=[];wrists=[]
    for i in range(72):
        t=i/6
        im=Image.new('RGB',(960,800),BG);d=ImageDraw.Draw(im)
        d.text((24,14),'Relay / Four asynchronous camera streams',font=BOLD,fill=WHITE)
        d.text((24,51),f'Historical simulator replay / {t:04.1f} of 12 seconds / original exposure order',font=FONT,fill=MUTED)
        for cam,rect,label in [
            ('head_left',(24,90,444,310),'Head left / pinhole / 120 deg'),
            ('head_right',(492,90,444,310),'Head right / pinhole / 120 deg'),
            ('wrist_left',(24,418,444,330),'Left wrist / circular fisheye / 180 deg'),
            ('wrist_right',(492,418,444,330),'Right wrist / circular fisheye / 180 deg')]:panel(im,replay,cam,t,rect,label)
        d.text((24,766),'6 fps sample / last delivered image held / simulated RGB / no new timing result',font=FONT,fill=MUTED)
        gallery.append(im)
        im=Image.new('RGB',(960,620),BG);d=ImageDraw.Draw(im)
        d.text((24,14),'Relay / Wrist-mounted fisheye views',font=BOLD,fill=WHITE)
        d.text((24,51),'Same recorded arm motion / 180-degree circular images / occlusion stays visible',font=FONT,fill=MUTED)
        panel(im,replay,'wrist_left',t,(24,90,444,470),'Left wrist')
        panel(im,replay,'wrist_right',t,(492,90,444,470),'Right wrist')
        d.text((24,585),'Simulated cameras / recorded RGB / RGB-only public excerpt / 12-second loop',font=FONT,fill=MUTED)
        wrists.append(im)
    target=ROOT/'docs/media'
    encode(gallery,target/'cameras.gif');encode(wrists,target/'wrists.gif')
    print(json.dumps({p.name:p.stat().st_size for p in [target/'cameras.gif',target/'wrists.gif']}))
    replay.close()

if __name__=='__main__':main()
