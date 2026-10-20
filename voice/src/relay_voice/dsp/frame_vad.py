"""Bounded causal Silero ONNX adapter, using the existing locked CPU runtime.

State/context protocol follows the MIT Silero wrapper at revision
1e261b036686cd0017d500ee96acd1c4ba572a9d. Its notice is kept beside the model.
No future samples or growing input queue are used: one fixed frame is filled.
"""
from functools import lru_cache
import hashlib
from pathlib import Path
import numpy as np

MODEL_SHA='1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3'

@lru_cache(maxsize=1)
def session():
    import onnxruntime as ort
    path=Path(__file__).resolve().parents[3]/'data/models/silero_vad/silero_vad.onnx'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==MODEL_SHA,'VAD model integrity mismatch'
    opts=ort.SessionOptions();opts.inter_op_num_threads=1;opts.intra_op_num_threads=1
    return ort.InferenceSession(str(path),sess_options=opts,providers=['CPUExecutionProvider'])

class FrameVAD:
    def __init__(self):
        self.session=session();self.reset()
    def reset(self):
        self.state=np.zeros((2,1,128),np.float32);self.context=np.zeros(64,np.float32)
        self.frame=np.zeros(512,np.float32);self.count=0;self.probability=0.
    def push(self,x):
        pos=0
        while pos<len(x):
            take=min(len(x)-pos,512-self.count)
            self.frame[self.count:self.count+take]=x[pos:pos+take]
            self.count+=take;pos+=take
            if self.count==512:
                inp=np.concatenate([self.context,self.frame])[None]
                prob,self.state=self.session.run(None,{'input':inp,'state':self.state,'sr':np.array(16000,dtype='int64')})
                self.probability=float(prob[0,0]);self.context[:]=self.frame[-64:];self.count=0
        return self.probability
