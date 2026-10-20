"""Causal adaptive energy VAD, bounded decision history and optional WOLA filter.

Energy decisions can optionally be supplemented by a causal speech classifier.
Very quiet speech and nonstationary noise remain ambiguous on a single channel.
"""
import numpy as np
from scipy.signal import butter,sosfilt


class NoiseControl:
    def __init__(self, sample_rate, config, delay_samples=0):
        self.sr=sample_rate;self.hop=sample_rate//200;self.config=config
        self.base_delay=int(delay_samples)
        cutoff=config.get('detector_highpass_hz',0)
        self.detector_sos=butter(2,cutoff,btype='highpass',fs=sample_rate,output='sos') if cutoff else None
        audio_cutoff=config.get('input_highpass_hz',0)
        self.audio_sos=butter(2,audio_cutoff,btype='highpass',fs=sample_rate,output='sos') if audio_cutoff else None
        if config.get('learned_vad',False):
            assert sample_rate==16000,'The learned detector is for the neural ingress only'
            from .frame_vad import FrameVAD
            self.vad=FrameVAD()
        else:self.vad=None
        self.reset()

    def reset(self):
        c=self.config
        if self.vad is not None:self.vad.reset()
        self.floor=float(c['initial_floor_rms']);self.open=False;self.hang=0
        self.gain=0.;self.minimum=float('inf');self.age=0
        self.energies=np.zeros(max(1,round(c['analysis_ms']/5)))
        self.energy_position=0
        self.detector_state=np.zeros((len(self.detector_sos),2)) if self.detector_sos is not None else None
        self.audio_state=np.zeros((len(self.audio_sos),2)) if self.audio_sos is not None else None
        self.spectral_decided=not c.get('adaptive_spectral',False)
        self.spectral_enabled=c.get('spectral',False) and self.spectral_decided
        self.delay=self.base_delay-(3*self.hop if c.get('spectral',False) and not self.spectral_decided else 0)
        self.quiet_frames=0
        self.delay_state=np.zeros(self.delay,np.float32)
        self.history=np.zeros(32768,np.float32);self.written=0;self.consumed=0
        self.frame=np.zeros(4*self.hop);self.ola=np.zeros(4*self.hop)
        self.window=np.sqrt(np.hanning(4*self.hop+1)[:-1])
        self.noise_power=np.zeros(2*self.hop+1);self.spectral_ready=False

    def analyse(self,x):
        assert len(x)%self.hop==0
        masks=[];filtered=[];c=self.config
        for pos in range(0,len(x),self.hop):
            block=x[pos:pos+self.hop]
            probability=self.vad.push(block) if self.vad is not None else 0.
            learned_speech=self.vad is not None and probability>=c.get('vad_off_probability' if self.open else 'vad_on_probability',.2 if self.open else .35)
            detector=block
            if self.detector_sos is not None:
                detector,self.detector_state=sosfilt(self.detector_sos,block,zi=self.detector_state)
            self.energies[self.energy_position]=float(np.mean(detector*detector))
            self.energy_position=(self.energy_position+1)%len(self.energies)
            rms=float(np.sqrt(np.mean(self.energies)))
            self.minimum=min(self.minimum,rms);self.age+=1
            # Track averaged quiet energy rather than five-millisecond minima:
            # a 50 Hz hum has near-zero instantaneous crossings, not silence.
            if not self.open and not learned_speech:self.floor+=.025*(rms-self.floor)
            self.floor=max(float(c['minimum_floor_rms']),self.floor)
            on=max(c['absolute_on_rms'],self.floor*c['on_ratio'])
            off=max(c['absolute_off_rms'],self.floor*c['off_ratio'])
            if learned_speech or rms>=(off if self.open else on):
                self.open=True;self.hang=round(c['hangover_ms']/5)
            elif self.hang>0:self.hang-=1
            else:self.open=False
            if not self.open:self.quiet_frames+=1
            if not self.spectral_decided and self.age>=50:
                self.spectral_decided=True
                self.spectral_enabled=not self.open and self.quiet_frames>=40 and self.floor>=.0005 and rms>=.0005
                if self.spectral_enabled:
                    self.delay+=3*self.hop
                    self.delay_state=np.pad(self.delay_state,(3*self.hop,0))
            target=1. if self.open else 0.
            step=1./max(1,round(self.sr*c['fade_ms']/1000))
            gains=np.clip(self.gain+(1 if target else -1)*step*np.arange(1,self.hop+1),0,1).astype(np.float32)
            self.gain=float(gains[-1]);masks.append(gains)
            if self.audio_sos is not None:
                block,self.audio_state=sosfilt(self.audio_sos,block,zi=self.audio_state)
            if c.get('spectral',False):
                self.frame[:-self.hop]=self.frame[self.hop:];self.frame[-self.hop:]=block
                spec=np.fft.rfft(self.frame*self.window);power=abs(spec)**2
                if not self.open:
                    self.noise_power=(.9*self.noise_power+.1*power) if self.spectral_ready else power
                    self.spectral_ready=True
                gain=np.sqrt(np.maximum(c.get('spectral_floor',.36),1-c.get('spectral_subtraction',.75)*self.noise_power/np.maximum(power,1e-15)))
                self.ola+=np.fft.irfft(spec*gain,n=len(self.frame))*self.window
                filtered.append((self.ola[:self.hop]/2).copy() if self.spectral_enabled else block)
                self.ola[:-self.hop]=self.ola[self.hop:];self.ola[-self.hop:]=0
            else:filtered.append(block)
        mask=np.concatenate(masks)
        pre=round(self.sr*c.get('pre_roll_ms',0)/1000)
        if pre:
            # Backfill only decisions whose audio has not been generated yet.
            # MeanVC already supplies this causal time margin; no future input
            # is requested and emitted output is never revised.
            rising=np.flatnonzero((mask>0)&(np.r_[self.history[(self.written-1)%len(self.history)] if self.written else 0,mask[:-1]]==0))
            for pos in rising:
                absolute=max(self.consumed,self.written+int(pos)-pre)
                end=min(len(mask),int(pos)+round(self.sr*c['fade_ms']/1000))
                local=max(0,absolute-self.written);indices=self.written+np.arange(local,end)
                ramp=np.minimum(1.,(indices-absolute+1)/max(1,round(self.sr*c['fade_ms']/1000)))
                mask[local:end]=np.maximum(mask[local:end],ramp)
                if absolute<self.written:
                    indices=np.arange(absolute,self.written)
                    ramp=np.minimum(1.,(indices-absolute+1)/max(1,round(self.sr*c['fade_ms']/1000)))
                    self.history[indices%len(self.history)]=np.maximum(self.history[indices%len(self.history)],ramp)
        assert self.written+len(mask)-self.consumed<=len(self.history),'VAD history exhausted'
        self.history[(self.written+np.arange(len(mask)))%len(self.history)]=mask
        self.written+=len(mask)
        # Do not gate the analysis input: output gating preserves low-energy
        # terminal consonants while the hangover drains the voice stage.
        return np.concatenate(filtered).astype(np.float32),mask

    def output_mask(self,n):
        assert self.consumed+n<=self.written,'VAD decision requested before input exists'
        mask=self.history[(self.consumed+np.arange(n))%len(self.history)].copy()
        self.consumed+=n
        if self.delay:
            joined=np.concatenate([self.delay_state,mask])
            result=joined[:n].copy();self.delay_state=joined[n:].copy()
            return result
        return mask

    def rebase(self):
        """Reset content indices after drained model silence; retain noise/VAD."""
        self.history.fill(0);self.written=0;self.consumed=0
        self.delay_state.fill(0)
