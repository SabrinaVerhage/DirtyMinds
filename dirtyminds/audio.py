"""Small, local PCM cleanup; no audio service or extra dependency required."""
from array import array
import math
import sys

SAMPLE_RATE = 24000
PLAYBACK_VERSION = "smooth-edges-rumble-v1"


def prepare_playback_pcm(pcm, *, reduce_rumble=False):
    """Smooth mono signed-16-bit LE audio without trimming or boosting it.

    Whisper cleanup rolls off low rumble below 90 Hz. It is not a noise gate:
    quiet breaths are retained, and no artificial background sound is added.
    """
    if not pcm or len(pcm) % 2:
        raise ValueError("Expected nonempty 16-bit PCM audio.")
    source = array("h")
    source.frombytes(pcm)
    if sys.byteorder != "little":
        source.byteswap()
    samples = array("d", source)
    if reduce_rumble:
        # Fourth-order Butterworth high-pass, as two biquad sections.
        # Coefficients: https://www.w3.org/TR/audio-eq-cookbook/#hpf
        omega = 2 * math.pi * 90 / SAMPLE_RATE
        cosine = math.cos(omega)
        for quality in (1 / (2 * math.cos(math.pi / 8)),
                        1 / (2 * math.cos(3 * math.pi / 8))):
            alpha = math.sin(omega) / (2 * quality)
            a0 = 1 + alpha
            b0 = (1 + cosine) / (2 * a0)
            b1 = -(1 + cosine) / a0
            a1, a2 = -2 * cosine / a0, (1 - alpha) / a0
            x1 = x2 = y1 = y2 = 0.0
            for i, sample in enumerate(samples):
                value = b0 * sample + b1 * x1 + b0 * x2 - a1 * y1 - a2 * y2
                samples[i] = value
                x2, x1, y2, y1 = x1, sample, y1, value

    # Raised-cosine edges settle exactly at zero, including each phrase/silence
    # boundary. Cap fades for very short clips; never remove samples or words.
    half = len(samples) // 2
    fade_in = min(SAMPLE_RATE * 20 // 1000, half)
    fade_out = min(SAMPLE_RATE * 120 // 1000, half)
    for count, reverse in ((fade_in, False), (fade_out, True)):
        for i in range(count):
            gain = (1 - math.cos(math.pi * i / max(1, count - 1))) / 2
            index = len(samples) - 1 - i if reverse else i
            samples[index] *= gain
    samples[0] = samples[-1] = 0.0

    # Filtering can overshoot. Reduce only when needed, never normalize quiet
    # material upward or hard-clip the result.
    peak = max(abs(x) for x in samples)
    gain = min(1.0, 32760 / max(1.0, peak))
    result = array("h", (round(x * gain) for x in samples))
    if sys.byteorder != "little":
        result.byteswap()
    return result.tobytes()
