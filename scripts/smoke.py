"""Offline default audio and bounded original camera/state publisher replay."""
from pathlib import Path
import argparse,json,subprocess,sys,os
ROOT=Path(__file__).resolve().parents[1]
for p in ['voice/src','voice','scene_robot']:sys.path.insert(0,str(ROOT/p))

def main():
    p=argparse.ArgumentParser();p.add_argument('--make-only',action='store_true');a=p.parse_args()
    import numpy as np,soundfile as sf
    from relay_voice.rt.engine import Pipeline
    from synthetic_episode import generate
    out=ROOT/'outputs';out.mkdir(exist_ok=True)
    t=np.arange(48000)/48000
    probe=(.08*np.sin(2*np.pi*180*t)+.02*np.sin(2*np.pi*360*t)).astype(np.float32)
    processor=Pipeline('v8',ROOT/'voice/configs/v8a_B.yaml')
    y=np.concatenate([processor.process48(probe[i:i+240]) for i in range(0,len(probe),240)])
    assert y.shape==probe.shape and np.isfinite(y).all() and .001<np.max(np.abs(y))<=1
    sf.write(out/'probe_robot.wav',y,48000)
    episode=generate(out/'synthetic_episode',ROOT/'scene_robot')
    if not a.make_only:
        env={**os.environ,'PYTHONPATH':str(ROOT/'scene_robot')}
        subprocess.run([sys.executable,'-m','p2.io.replay_node',str(episode),'--speed','10','--seconds','.5','--output-log',str(out/'replay.json')],cwd=ROOT/'scene_robot',env=env,check=True)
        replay=json.loads((out/'replay.json').read_text())
        assert replay['counts']=={'joints':20,'odom':20,'frame':80},replay['counts']
    result={'passed':True,'audio_samples':len(y),'replay_counts':None if a.make_only else replay['counts'],
            'scope':'Synthetic functional replay; no performance, physical audio, human listening or GPU validation.'}
    (out/'smoke.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))

if __name__=='__main__':main()
