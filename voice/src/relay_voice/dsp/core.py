import numpy as np
from numba import njit


@njit(cache=True)
def yin(frame, sample_rate=16000., fmin=70., fmax=500.):
    maxlag = min(int(sample_rate / fmin) + 2, len(frame)//2)
    minlag = max(2, int(sample_rate/fmax))
    difference = np.zeros(maxlag+1)
    size = len(frame)-maxlag
    running = 0.0
    for lag in range(1, maxlag+1):
        value = 0.0
        for i in range(size):
            d = frame[i]-frame[i+lag]
            value += d*d
        running += value
        difference[lag] = value*lag/max(running, 1e-18)
    chosen = minlag
    found = False
    for lag in range(minlag, maxlag-1):
        if difference[lag] < 0.15:
            chosen = lag
            while chosen+1 < maxlag and difference[chosen+1] < difference[chosen]:
                chosen += 1
            found = True
            break
    if not found:
        chosen = minlag + np.argmin(difference[minlag:maxlag])
    offset = 0.0
    if 1 < chosen < maxlag:
        a, b, c = difference[chosen-1], difference[chosen], difference[chosen+1]
        den = a-2*b+c
        if abs(den) > 1e-12:
            offset = min(0.5, max(-0.5, 0.5*(a-c)/den))
    confidence = max(0., min(1., 1.-difference[chosen]))
    return sample_rate/(chosen+offset), confidence


@njit(cache=True)
def levinson(r, order):
    a = np.zeros(order+1)
    a[0] = 1.
    error = max(r[0], 1e-12)
    for k in range(1, order+1):
        reflection = -r[k]
        for j in range(1, k):
            reflection -= a[j]*r[k-j]
        reflection = max(-0.98, min(0.98, reflection/error))
        old = a.copy()
        for j in range(1, k):
            a[j] = old[j]+reflection*old[k-j]
        a[k] = reflection
        error = max(error*(1-reflection*reflection), 1e-12)
    return a, error


@njit(cache=True)
def autocorrelation(x, order):
    r = np.zeros(order+1)
    for lag in range(order+1):
        for i in range(lag, len(x)):
            r[lag] += x[i]*x[i-lag]
    r[0] *= 1.0001
    return r


@njit(cache=True)
def divide_linear(a, sign):
    quotient = np.empty(len(a)-1)
    quotient[0] = a[0]
    for i in range(1, len(quotient)):
        quotient[i] = a[i]-sign*quotient[i-1]
    return quotient


def lpc_to_lsf(a):
    """Even-order stable LPC -> alternating line spectral frequencies."""
    p = np.r_[a, 0.] + np.r_[0., a[::-1]]
    q = np.r_[a, 0.] - np.r_[0., a[::-1]]
    p = divide_linear(p, 1.)
    q = divide_linear(q, -1.)
    angles = np.r_[np.angle(np.roots(p)), np.angle(np.roots(q))]
    lsf = np.sort(angles[(angles > 1e-5) & (angles < np.pi-1e-5)])
    if len(lsf) != len(a)-1:
        raise ValueError("LPC did not produce the required LSF pairs")
    return lsf


def lsf_to_lpc(lsf):
    p, q = np.array([1.]), np.array([1.])
    for w in lsf[::2]:
        p = np.convolve(p, [1., -2*np.cos(w), 1.])
    for w in lsf[1::2]:
        q = np.convolve(q, [1., -2*np.cos(w), 1.])
    a = .5*(np.convolve(p, [1., 1.])+np.convolve(q, [1., -1.]))
    return a[:-1]


@njit(cache=True)
def synthesize(excitation, previous_a, target_a, memory):
    """Stateful all-pole synthesis; sample smoothing between LSF substeps."""
    output = np.empty(len(excitation))
    order = len(memory)
    for i in range(len(excitation)):
        mix = (i+1)/len(excitation)
        value = excitation[i]
        for j in range(order):
            value -= ((1-mix)*previous_a[j+1]+mix*target_a[j+1])*memory[j]
        if not np.isfinite(value) or abs(value) > 100:
            value = 0.
            memory[:] = 0.
        for j in range(order-1, 0, -1):
            memory[j] = memory[j-1]
        memory[0] = value
        output[i] = value
    return output


@njit(cache=True)
def character_fx(signal, comb, position, feedback, depth, ring_hz, samples, gain):
    result = np.empty(len(signal), dtype=np.float32)
    for i in range(len(signal)):
        delayed = comb[position]
        value = signal[i]+feedback*delayed
        comb[position] = min(2., max(-2., value))
        position = (position+1)%len(comb)
        modulation = 1-depth+depth*np.cos(2*np.pi*ring_hz*(samples+i)/16000.)
        result[i] = np.tanh(value*modulation*gain)
    return result, position
