from pathlib import Path
import os,sys,json,subprocess
import numpy as np, soundfile as sf
from PIL import Image,ImageDraw,ImageFont
import imageio_ffmpeg
D=Path(__file__).resolve().parents[1];M=D/'docs/media'
sys.path[:0]=[str(D/'voice/src'),str(D/'voice')]
from eval.convert import read48,convert
os.environ['NUMBA_CACHE_DIR']=str(D/'cache/numba')
x=read48(M/'voice_input.wav');y,_,_=convert(x,'v8',D/'voice/configs/v8a_B.yaml')
assert np.isfinite(y).all() and np.max(np.abs(y))<=1
sf.write(M/'voice_robot.wav',y,48000,subtype='PCM_16')
# Rewrite the generated source WAV too; no ancillary recording metadata.
sf.write(M/'voice_input.wav',x,48000,subtype='PCM_16')
gap=np.zeros(24000,np.float32);combined=np.r_[x,gap,y]
sf.write(D/'outputs/comparison.wav',combined,48000)
font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',28)
small=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',20)
bold=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',42)
for kind,title,color in [('raw','Synthetic source',(100,202,188)),('robot','Default robot character',(234,183,124))]:
    im=Image.new('RGB',(1280,720),(17,28,37));draw=ImageDraw.Draw(im)
    draw.text((65,55),'Relay Workbench',font=bold,fill='white')
    draw.text((65,140),title,font=font,fill=color)
    draw.text((65,200),'Local CPU audio / causal DSP / synthetic speech',font=small,fill='#a8bdc7')
    lines=['Relay Workbench processes voice in small audio blocks.',
           'The robot character runs locally on the CPU.',
           'This example uses synthetic speech.']
    for i,line in enumerate(lines):draw.text((65,315+45*i),line,font=font,fill='white')
    draw.line((65,520,1215,520),fill=color,width=2)
    draw.text((65,560),'Functional demonstration; no latency or human listening claim.',font=small,fill='#a8bdc7')
    draw.text((65,600),'System TTS: Microsoft Hazel / same sentence in both segments',font=small,fill='#a8bdc7')
    im.save(D/'outputs'/f'{kind}.png')
duration=len(x)/48000
ff=imageio_ffmpeg.get_ffmpeg_exe()
subprocess.run([ff,'-y','-loglevel','error','-loop','1','-t',str(duration+.5),'-i',str(D/'outputs/raw.png'),
 '-loop','1','-t',str(duration),'-i',str(D/'outputs/robot.png'),'-i',str(D/'outputs/comparison.wav'),
 '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-map','2:a','-map_metadata','-1',
 '-c:v','libx264','-preset','fast','-crf','28','-pix_fmt','yuv420p','-r','10','-c:a','aac','-b:a','128k','-shortest','-movflags','+faststart',str(M/'voice_demo.mp4')],check=True)
def stamp(t):
    ms=round(t*1000);return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}'
text=(M/'narration.txt').read_text(encoding='utf-8-sig').strip()
(M/'voice_demo.srt').write_text(f'1\n{stamp(0)} --> {stamp(duration)}\nSynthetic source: {text}\n\n2\n{stamp(duration+.5)} --> {stamp(2*duration+.5)}\nDefault robot character: {text}\n',encoding='utf-8')
(D/'outputs/voice_media.json').write_text(json.dumps({'source':'Microsoft Hazel system TTS','script':text,'source_duration_s':duration,'video_duration_s':2*duration+.5,'human_recording':False,'original_target_embedding_used_for_this_dsp_demo':False},indent=2))
print(f'Generated {2*duration+.5:.2f}s neutral synthetic comparison; original input/output speech is excluded.')
