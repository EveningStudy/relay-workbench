"""Create only the approved silent input clip for the phone-pose demonstration."""
import argparse,json,subprocess
from pathlib import Path
import imageio_ffmpeg
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);args=parser.parse_args()
    target=ROOT/'docs/media/phone_excerpt.mp4'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-ss','6','-i',str(args.source),'-t','12','-an',
        '-map_metadata','-1','-vf','scale=960:-2,fps=15','-c:v','libx264','-crf','24','-pix_fmt','yuv420p',str(target)],check=True)
    print(json.dumps({'input_clip_bytes':target.stat().st_size,'next':'run.ps1 phone --prepare; then scripts/make_phone_pose_media.py'}))

if __name__=='__main__':main()
