"""UI-owned recorder child, with bounded names and a graceful ZMQ stop."""
from pathlib import Path
import os
import re
import subprocess
import sys


class RecordSession:
    def __init__(self,cameras='configs/cameras.yaml',fusion='configs/fusion.yaml'):
        self.process=None
        self.log=None
        self.path=None
        self.cameras=cameras;self.fusion=fusion
        self.synthetic_acceptance=os.environ.get('P2_SYNTHETIC_ACCEPTANCE')=='1'

    def start(self,name):
        from p2.io.frozen_build import check
        check(required=self.synthetic_acceptance,candidate=self.synthetic_acceptance)
        if self.process and self.process.poll() is None:raise ValueError('Already recording')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',name):
            raise ValueError('Use letters, numbers, underscores or hyphens; start with a letter or number')
        self.path=Path('data/m22/f_acceptance' if self.synthetic_acceptance else 'human_inputs/07_teleop')/name
        if self.path.exists():raise ValueError('That episode already exists. Choose a new name.')
        self.log=open('data/logs/teleop_recorder.txt','w')
        self.process=subprocess.Popen([sys.executable,'-u','-m','p2.io.recorder','--output',str(self.path),
            '--origin','scripted' if self.synthetic_acceptance else 'teleop',
            '--operator','automated_acceptance' if self.synthetic_acceptance else 'operator',
            '--control','--cameras',str(self.cameras),'--fusion',str(self.fusion)],stdout=self.log,stderr=subprocess.STDOUT)
        return str(self.path)

    def close(self):
        if self.process:
            try:self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=5)
        if self.log:self.log.close()
