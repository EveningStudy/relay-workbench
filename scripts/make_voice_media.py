"""Render the approved two-speaker VCTK comparison from bundled source WAVs."""
from pathlib import Path
import hashlib, json, os, subprocess, sys
import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / 'docs/media'
os.environ['NUMBA_CACHE_DIR'] = str(ROOT / 'cache/numba')
sys.path[:0] = [str(ROOT / 'voice/src'), str(ROOT / 'voice')]
from eval.convert import read48, convert


def stamp(t):
    ms = round(t * 1000)
    return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}'


def main():
    manifest = json.loads((MEDIA / 'voice_sources.json').read_text())
    font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 26)
    small = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 19)
    bold = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 40)
    rate, fps = 48000, 12
    segments, subtitles = [], []
    for clip in manifest['clips']:
        source = MEDIA / clip['file']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == clip['sha256']
        x = read48(source)
        y, _, _ = convert(x, 'v8', ROOT / 'voice/configs/v8a_B.yaml')
        assert np.isfinite(y).all() and np.max(np.abs(y)) <= 1
        for label, audio in [('Original recording', x), ('Default robot character', y)]:
            count = int(np.ceil((len(audio) / rate + .6) * fps))
            padded = np.pad(audio, (0, count * (rate // fps) - len(audio)))
            segments.append((clip, label, audio, padded, count))
    combined = np.concatenate([s[3] for s in segments])
    work = ROOT / 'outputs/voice_media'
    work.mkdir(parents=True, exist_ok=True)
    sf.write(work / 'comparison.wav', combined, rate, subtype='PCM_16')
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    process = subprocess.Popen([ff, '-y', '-loglevel', 'error', '-f', 'rawvideo',
        '-pixel_format', 'rgb24', '-video_size', '1280x720', '-framerate', str(fps),
        '-i', '-', '-i', str(work / 'comparison.wav'), '-map_metadata', '-1',
        '-c:v', 'libx264', '-crf', '26', '-preset', 'fast', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '128k', '-shortest', '-movflags', '+faststart',
        str(MEDIA / 'voice_demo.mp4')], stdin=subprocess.PIPE)
    elapsed = 0
    for clip, label, audio, padded, count in segments:
        duration = count / fps
        subtitles.append(f'{len(subtitles)+1}\n{stamp(elapsed)} --> {stamp(elapsed+len(audio)/rate)}\n'
                         f"{clip['speaker']} / {label}: {clip['text']}\n")
        color = '#64cabc' if label == 'Original recording' else '#eab77c'
        peaks = [float(np.max(np.abs(b))) if len(b) else 0 for b in np.array_split(audio, 550)]
        for frame in range(count):
            im = Image.new('RGB', (1280, 720), '#111c25')
            draw = ImageDraw.Draw(im)
            draw.text((60, 40), 'Relay Workbench / Voice', font=bold, fill='white')
            draw.text((60, 105), f"{clip['speaker']}  /  {label}", font=font, fill=color)
            draw.text((60, 153), 'Same recording before and after the local CPU DSP pipeline', font=small, fill='#a8bdc7')
            progress = min(1, frame / fps / (len(audio) / rate))
            for i, peak in enumerate(peaks):
                xpos = 65 + i * 2.08; height = max(1, peak * 150)
                draw.line((xpos, 290-height, xpos, 290+height), fill=color if i/550 <= progress else '#3a4d5a', width=2)
            draw.line((65+1144*progress, 205, 65+1144*progress, 375), fill='white', width=2)
            draw.text((60, 420), 'Six spoons of fresh snow peas, five thick slabs of blue cheese,', font=font, fill='white')
            draw.text((60, 460), 'and maybe a snack for her brother Bob.', font=font, fill='white')
            draw.text((60, 548), 'CSTR VCTK 0.92 / p226_003_mic2 + p237_003_mic2 / CC BY 4.0', font=small, fill='#a8bdc7')
            draw.text((60, 580), 'Yamagishi, Veaux & MacDonald (2019), University of Edinburgh CSTR', font=small, fill='#a8bdc7')
            draw.text((60, 612), 'doi.org/10.7488/ds/2645 / Audio adapted with DSP; no endorsement implied.', font=small, fill='#a8bdc7')
            draw.text((60, 650), 'Illustrative comparison; not a new quality or latency measurement.', font=small, fill='#a8bdc7')
            process.stdin.write(im.tobytes())
        elapsed += duration
    process.stdin.close()
    assert process.wait() == 0
    (MEDIA / 'voice_demo.srt').write_text('\n'.join(subtitles), encoding='utf-8')
    print(json.dumps({'duration_s': elapsed, 'speakers': 2, 'source': 'CSTR VCTK 0.92', 'system': 'v8 / v8a_B.yaml', 'speech_trimmed': False, 'speech_normalized': False}))


if __name__ == '__main__':
    main()
