"""Causal B-derived vocoder with bounded target-envelope adaptation."""
from pathlib import Path
import numpy as np
from scipy.signal import sosfilt
from relay_voice.systems.crisp_robot import CrispRobot
from relay_voice.rt.engine import Pipeline


class NormalizedRobot(CrispRobot):
    name="v9_dsp_b"
    # The causal isolated-spike detector emits the preceding sample.
    algorithmic_delay_ms=15.0+1000/24000

    def __init__(self,config):
        super().__init__(config)
        c=self.config
        target=Path(c["target_envelope"])
        self.target_power=np.load(target)
        assert self.target_power.shape==(self.size//2+1,)
        self.ltas=self.target_power.copy()
        self.freq=np.fft.rfftfreq(self.size,1/self.sample_rate)
        self.band=(self.freq>=300)&(self.freq<=3500)
        self.target_centroid=float(self.freq[self.band]@self.target_power[self.band]/self.target_power[self.band].sum())
        self.hop_index=np.arange(self.hop)
        self.frame_index=np.arange(self.size)
        self.lags=np.arange(48,343)
        self.pitch_values=np.full(5,c["f0_hz"],dtype=float)
        self.pitch_count=0
        self.source_pitch=c["f0_hz"]
        self.log_mean=np.log(c["f0_hz"])
        self.log_variance=.08
        self.previous=np.zeros(2)
        self.click_count=0
        self.pitch_rejections=0
        self.gate=0.0
        self.quiet=100
        self.adapt=60
        self.warp=1.0
        self.eq=np.ones_like(self.target_power)
        self.metal_state=0.0

    def process_block(self,x):
        if x.shape!=(self.hop,): raise ValueError("V9 DSP expects a 24 kHz 5 ms block")
        c=self.config
        joined=np.r_[self.previous,x]
        left,middle,right=joined[:-2],joined[1:-1],joined[2:]
        neighbour=.5*(left+right)
        deviation=np.abs(middle-neighbour)
        threshold=max(c["click_threshold"],6*float(np.sqrt(np.mean(np.diff(joined)**2))))
        clicks=(deviation>threshold)&(np.abs(left-right)<deviation*.3)
        cleaned=np.where(clicks,neighbour,middle)
        self.previous[:]=joined[-2:]
        self.click_count+=int(clicks.sum())
        x,self.hp_state=sosfilt(self.hp,cleaned,zi=self.hp_state)
        self.history[:-self.hop]=self.history[self.hop:]
        self.history[-self.hop:]=x
        self.pitch_history[:-self.hop]=self.pitch_history[self.hop:]
        self.pitch_history[-self.hop:]=x
        rms=float(np.sqrt(np.mean(self.history**2)))
        gate_target=float(np.clip((rms-c["gate_floor"])/(c["gate_floor"]*3),0,1))
        self.gate+=(.8 if gate_target>self.gate else .18)*(gate_target-self.gate)
        if rms<c["gate_floor"]*3:
            self.quiet+=1
        else:
            if self.quiet>=40: self.adapt=60
            self.quiet=0
        p=self.pitch_history-self.pitch_history.mean()
        corr=np.fft.irfft(np.abs(np.fft.rfft(p,n=2048))**2)
        energy=np.r_[0.,np.cumsum(p*p)]
        denom=np.sqrt(np.maximum((energy[-1]-energy[self.lags])*energy[-1-self.lags],0))
        periodic=corr[self.lags]/np.maximum(denom,1e-12)
        confidence=float(np.max(periodic))
        raw_pitch=self.sample_rate/float(self.lags[np.argmax(periodic)])
        target=np.clip((confidence-.32)/.30,0,1)*gate_target
        self.voicing+=(.65 if target>self.voicing else .5)*(target-self.voicing)
        if confidence>.65 and gate_target>.8:
            median=float(np.median(self.pitch_values[:min(self.pitch_count,5)])) if self.pitch_count else raw_pitch
            if max(raw_pitch/median,median/raw_pitch)>1.5:
                self.pitch_rejections+=1
                # Median-relative octave correction; the carrier remains fixed.
                while raw_pitch>median*1.5: raw_pitch/=2
                while raw_pitch<median/1.5: raw_pitch*=2
            self.pitch_values[self.pitch_count%5]=raw_pitch
            self.pitch_count+=1
            self.source_pitch=float(np.median(self.pitch_values[:min(self.pitch_count,5)]))
            delta=np.log(self.source_pitch)-self.log_mean
            self.log_mean+=.025*delta
            self.log_variance=.975*self.log_variance+.025*delta**2
        z=float(np.clip((np.log(max(self.source_pitch,1))-self.log_mean)/max(np.sqrt(self.log_variance),.08),-2,2))
        spectrum=np.fft.rfft(self.history*self.window)
        power=np.convolve(np.abs(spectrum)**2,self.kernel,mode="same")
        if gate_target>.8 and confidence>.55:
            # Normalise power before adaptation so level changes do not drive EQ.
            observed=power/max(float(power.sum()),1e-12)
            rate=.07 if self.adapt else .0125
            change=float(np.sqrt(np.mean((np.log(observed+1e-8)-np.log(self.ltas+1e-8))**2)))
            if change>1.7: self.adapt=60
            self.ltas+=(rate)*(observed-self.ltas)
        if self.adapt: self.adapt-=1
        centroid=float(self.freq[self.band]@self.ltas[self.band]/max(self.ltas[self.band].sum(),1e-12))
        desired=np.clip(centroid/self.target_centroid,.8,1.25)**c["warp_strength"]
        self.warp+=.05*(desired-self.warp)
        warped=np.interp(self.freq*self.warp,self.freq,power)
        source_ltas=np.interp(self.freq*self.warp,self.freq,self.ltas)
        desired_eq=np.clip(np.sqrt(self.target_power/np.maximum(source_ltas,1e-8)),.35,2.8)**c["ltas_strength"]
        self.eq+=.05*(desired_eq-self.eq)
        envelope=np.sqrt(np.maximum(warped,0))*self.eq
        carrier=self.carrier[(self.frame_index+self.clock-self.size+self.hop)%self.period]
        cs=np.fft.rfft(carrier*self.window)
        ce=np.sqrt(np.convolve(np.abs(cs)**2,self.kernel,mode="same"))
        robot=cs*envelope/np.maximum(ce,1e-8)
        mix=c["vocoder_mix"]*self.voicing*self.wet_band
        # The same smooth EQ also acts on the retained low-band residual.
        dry_eq=1+(self.eq-1)*self.wet_band*c["dry_eq_strength"]
        frame=np.fft.irfft(spectrum*dry_eq*(1-mix)+robot*mix,n=self.size)
        self.ola+=frame*self.window
        output=self.ola[:self.hop].copy()/2
        self.ola[:-self.hop]=self.ola[self.hop:]
        self.ola[-self.hop:]=0
        delayed=np.r_[self.comb,output]
        self.metal_state+=.5*(self.voicing**2*gate_target-self.metal_state)
        metallic=output+c["metal_mix"]*self.metal_state*delayed[:self.hop]
        self.comb[:]=delayed[-self.comb_samples:]
        output=.88*np.tanh(c["output_gain"]*metallic/.88)*self.gate
        if self.gate<1e-6: output.fill(0)
        self.clock=(self.clock+self.hop)%self.period
        self.last={"confidence":confidence,"source_f0":self.source_pitch,"output_f0":c["f0_hz"],
                   "relative_z":z,"warp":self.warp,"gate":self.gate,"clicks_removed":self.click_count,
                   "pitch_octave_corrections":self.pitch_rejections,"adaptation_fast":bool(self.adapt)}
        return output.astype(np.float32)


class DSPPipeline(Pipeline):
    def __init__(self,config):
        super().__init__("v8",config)
        self.system=NormalizedRobot(config)
