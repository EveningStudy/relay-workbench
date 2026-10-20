"""Rebuild the approved, silent 6-18 second excerpt from an owner-provided original."""
import argparse,json,subprocess
from pathlib import Path
import cv2
from PIL import Image,ImageDraw,ImageFont
import imageio_ffmpeg
from make_camera_media import encode,ROOT,BG,WHITE,MUTED

def main():
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);args=parser.parse_args()
    frames=[];capture=cv2.VideoCapture(str(args.source))
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',18)
    bold=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',25)
    for i in range(72):
        capture.set(cv2.CAP_PROP_POS_MSEC,(6+i/6)*1000);ok,frame=capture.read()
        if not ok:raise RuntimeError('Approved source interval could not be decoded')
        view=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)).resize((960,540))
        image=Image.new('RGB',(960,648),BG);image.paste(view,(0,72));draw=ImageDraw.Draw(image)
        draw.text((24,10),'Relay / Physical phone camera',font=bold,fill=WHITE)
        draw.text((24,43),'Approved 12-second excerpt / recorded RGB / silent',font=font,fill=MUTED)
        draw.text((24,621),'Real kitchen footage / no robot camera, depth or geometry-fusion claim',font=font,fill=MUTED)
        frames.append(image)
    capture.release();target=ROOT/'docs/media'
    encode(frames,target/'phone.gif')
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-ss','6','-i',str(args.source),'-t','12','-an',
        '-map_metadata','-1','-vf','scale=960:-2,fps=15','-c:v','libx264','-crf','24','-pix_fmt','yuv420p',str(target/'phone_excerpt.mp4')],check=True)
    print(json.dumps({p.name:p.stat().st_size for p in [target/'phone.gif',target/'phone_excerpt.mp4']}))

if __name__=='__main__':main()
