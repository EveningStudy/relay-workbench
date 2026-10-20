import numpy as np
import librosa
from scipy.signal import resample_poly
from transformers.models.whisper.english_normalizer import EnglishTextNormalizer
import jiwer


def error_counts(reference, hypothesis, normalizer):
    ref, hyp = normalizer(reference), normalizer(hypothesis)
    w, c = jiwer.process_words(ref, hyp), jiwer.process_characters(ref, hyp)
    return {"reference_normalized": ref, "hypothesis_normalized": hyp,
            "word_errors": w.substitutions + w.deletions + w.insertions,
            "words": w.hits + w.substitutions + w.deletions,
            "char_errors": c.substitutions + c.deletions + c.insertions,
            "chars": c.hits + c.substitutions + c.deletions}


def acoustic(audio16):
    if len(audio16) < 640:
        return {"f0_mean_hz": None, "f0_range_hz": None, "envelope_centroid_hz": None}
    f0 = librosa.yin(audio16, fmin=70, fmax=500, sr=16000, frame_length=640, hop_length=160, center=False)
    frames = librosa.util.frame(audio16, frame_length=640, hop_length=160)
    voiced = []
    centroids = []
    for i in range(frames.shape[1]):
        frame = frames[:, i]
        energy = float(frame @ frame)
        if energy / 640 < 1e-6:
            continue
        lag = int(16000 / f0[i])
        periodicity = float(frame[:-lag] @ frame[lag:]) / max(energy, 1e-12)
        if periodicity > 0.35:
            voiced.append(f0[i])
        spectrum = np.abs(np.fft.rfft(frame * np.hanning(640)))
        freq = np.fft.rfftfreq(640, 1/16000)
        centroids.append(float(freq @ spectrum / max(spectrum.sum(), 1e-12)))
    return {"f0_mean_hz": float(np.mean(voiced)) if voiced else None,
            "f0_range_hz": float(np.percentile(voiced, 95)-np.percentile(voiced, 5)) if voiced else None,
            "envelope_centroid_hz": float(np.mean(centroids)) if centroids else None}


def eer(embeddings, speakers):
    scores, labels = [], []
    for i in range(len(embeddings)):
        for j in range(i):
            scores.append(float(embeddings[i] @ embeddings[j]))
            labels.append(speakers[i] == speakers[j])
    scores, labels = np.asarray(scores), np.asarray(labels, dtype=bool)
    if not labels.any() or labels.all():
        return float("nan"), 0, 0
    order = np.argsort(-scores)
    labels, scores = labels[order], scores[order]
    endpoints = np.r_[np.where(np.diff(scores) != 0)[0], len(scores)-1]
    far = np.r_[0, np.cumsum(~labels)[endpoints] / sum(~labels)]
    frr = np.r_[1, 1 - np.cumsum(labels)[endpoints] / sum(labels)]
    delta = far - frr
    k = np.where(delta >= 0)[0][0]
    if k == 0:
        value = (far[0] + frr[0]) / 2
    else:
        weight = -delta[k-1] / (delta[k]-delta[k-1])
        value = far[k-1] + weight * (far[k]-far[k-1])
    return float(value), int(sum(labels)), int(sum(~labels))


def clustered_ci(rows, error="word_errors", denom="words", repetitions=1000):
    speakers = sorted({r["speaker"] for r in rows})
    counts = np.array([[sum(r[error] for r in rows if r["speaker"] == s),
                        sum(r[denom] for r in rows if r["speaker"] == s)] for s in speakers])
    rng = np.random.default_rng(20261016)
    selected = counts[rng.integers(len(speakers), size=(repetitions, len(speakers)))].sum(axis=1)
    ratios = selected[:, 0] / np.maximum(selected[:, 1], 1)
    return list(map(float, np.percentile(ratios, [2.5, 97.5])))
