"""DNSMOS P.835/P.808 local CPU scoring; official preprocessing/calibration."""
from pathlib import Path
import numpy as np
import librosa
import onnxruntime as ort


class DNSMOS:
    def __init__(self,folder):
        options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
        self.primary=ort.InferenceSession(str(Path(folder)/"sig_bak_ovr.onnx"),options,providers=["CPUExecutionProvider"])
        self.p808=ort.InferenceSession(str(Path(folder)/"model_v8.onnx"),options,providers=["CPUExecutionProvider"])

    def score(self,audio16):
        audio=np.asarray(audio16,dtype=np.float32)
        while len(audio)<144160: audio=np.r_[audio,audio]
        hops=int(np.floor(len(audio)/16000)-9.01)+1
        rows=[]
        for i in range(hops):
            segment=audio[i*16000:i*16000+144160]
            if len(segment)<144160:continue
            mel=librosa.feature.melspectrogram(y=segment[:-160],sr=16000,n_fft=321,hop_length=160,n_mels=120)
            mel=((librosa.power_to_db(mel,ref=np.max)+40)/40).T[None].astype(np.float32)
            sig,bak,overall=self.primary.run(None,{self.primary.get_inputs()[0].name:segment[None]})[0][0]
            p808=float(self.p808.run(None,{self.p808.get_inputs()[0].name:mel})[0][0][0])
            rows.append([float(np.polyval([-.08397278,1.22083953,.0052439],sig)),
                         float(np.polyval([-.13166888,1.60915514,-.39604546],bak)),
                         float(np.polyval([-.06766283,1.11546468,.04602535],overall)),p808])
        result=np.mean(rows,axis=0)
        return dict(zip(("dnsmos_sig","dnsmos_bak","dnsmos_ovrl","dnsmos_p808"),map(float,result)))
