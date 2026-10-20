"""Fingerprint the recording build without including generated evidence or human inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import importlib.metadata
from p2.io.recorder import code_hash,config_hash

PATH=Path('docs/evidence/frozen_build.json')
CANDIDATE=Path('docs/evidence/m22_f_candidate.json')
# Runtime file reads audited in operator_ui, SplatView, build_world/texture,
# robot/FK, recorder and realcam_node. Generated OBJ files are recreated from
# frozen scene/source before use; their outputs belong to the evidence manifest.
INPUTS=('assets/scan/old_map.ply','assets/scan/real_desktop_texture.png',
        'assets/scan/alignment.json','data/realcam/video_validation/validation.json',
        'data/realcam/phone_calibration.json','human_inputs/02_measurements.yaml')


def fingerprint():
    files=[*Path('p2').rglob('*.py'),*Path('configs').rglob('*.yaml'),*Path('scripts').glob('*'),*Path('assets/robot').glob('*')]
    files += [Path(x) for x in ['env.ps1','pyproject.toml','uv.lock']]
    files += [Path(x) for x in INPUTS]
    hashes={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files) if p.is_file()}
    return {'code_hash':code_hash(),'config_hash':config_hash(),'files':hashes,
        'build_hash':hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()}


def check(required=False,candidate=False):
    path=CANDIDATE if candidate else PATH
    if not path.exists():
        if required:raise ValueError('No validated recording build declared. Wait for M22 F acceptance.')
        return None
    saved=json.loads(path.read_text());current=fingerprint()
    changed=[name for name in set(saved['files'])|set(current['files']) if saved['files'].get(name)!=current['files'].get(name)]
    if changed:raise ValueError('Frozen build changed; recordings must wait for a refreshed freeze: '+', '.join(sorted(changed)))
    assert saved['build_hash']==current['build_hash']
    return saved


def main():
    p=argparse.ArgumentParser();group=p.add_mutually_exclusive_group()
    group.add_argument('--create',action='store_true');group.add_argument('--prepare',action='store_true');group.add_argument('--check',action='store_true')
    p.add_argument('--candidate',action='store_true');a=p.parse_args()
    if a.create or a.prepare:
        if PATH.exists():raise ValueError('Freeze already exists; retain it until human integration is explicitly started.')
        if a.prepare and CANDIDATE.exists():raise ValueError('Candidate exists; preserve it instead of overwriting')
        missing=[x for x in INPUTS if not Path(x).is_file()]
        if missing:raise ValueError('Missing runtime/calibration inputs: '+', '.join(missing))
        if a.create:
            pending=check(required=True,candidate=True)
            acceptance=json.loads(Path('docs/evidence/m22_f_launcher.json').read_text())
            assert acceptance['pass'] and acceptance['candidate_build_hash']==pending['build_hash']
            assert acceptance['synthetic_acceptance_only']
            evidence=json.loads(Path('docs/evidence/m22_evidence_manifest.json').read_text())
            assert evidence['operating_build_hash']==pending['build_hash']
        result={**fingerprint(),'frozen_at_ns':time.time_ns(),'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'status':'Validation candidate only; not ready to record' if a.prepare else 'Chris: record now',
            'tool_versions':{n:importlib.metadata.version(n) for n in ('sapien','viser','numpy','opencv-python','pyzmq','torch','playwright')},
            'scope':'Conservative full p2/config/scripts/toolchain/robot identity plus runtime scan/texture and calibration inputs. No evaluation directory is silently excluded. New human recordings and generated reports are outside this identity.'}
        (CANDIDATE if a.prepare else PATH).write_text(json.dumps(result,indent=2))
    else:result=check(required=True,candidate=a.candidate)
    print(json.dumps({k:result[k] for k in ['status','code_commit','code_hash','config_hash','build_hash']},indent=2))


if __name__=='__main__':main()
