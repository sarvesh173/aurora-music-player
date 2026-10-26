"""Small, dependency-free 10-band equalizer primitives."""

import math
from typing import Iterable, List, Optional, Sequence


EQ_BANDS_HZ = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
EQ_MIN_GAIN = -12
EQ_MAX_GAIN = 12
EQ_PRESETS = {
    "Flat": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "Bass Boost": [8, 6, 4, 2, 0, 0, 0, 0, 0, 0],
    "Treble Boost": [0, 0, 0, 0, 0, 0, 2, 4, 6, 8],
    "Vocal": [-2, -2, 0, 2, 4, 4, 3, 1, 0, -1],
    "Acoustic": [2, 2, 1, 2, 3, 2, 3, 3, 2, 1],
    "Rock": [4, 3, 0, -1, -2, 0, 2, 3, 4, 4],
    "Pop": [-1, 1, 3, 3, 1, 0, -1, -1, 1, 2],
    "Jazz": [3, 2, 1, 0, -1, -1, 0, 1, 2, 3],
    "Classical": [4, 3, 2, 0, -1, -1, 0, 2, 3, 4],
    "Electronic": [5, 4, 1, 0, -2, 2, 1, 1, 4, 5],
    "Loudness": [6, 4, 0, 0, -2, 0, 0, 2, 4, 6],
}


def normalize_gains(gains: Optional[Iterable[float]]) -> List[int]:
    values = list(gains or [])[: len(EQ_BANDS_HZ)]
    result: List[int] = []
    for value in values:
        try:
            value = int(round(float(value)))
        except (TypeError, ValueError):
            value = 0
        result.append(max(EQ_MIN_GAIN, min(EQ_MAX_GAIN, value)))
    result.extend([0] * (len(EQ_BANDS_HZ) - len(result)))
    return result


class EqualizerDSP:
    """Stateful peaking-filter chain suitable for PCM buffers.

    The player keeps Qt Multimedia as its low-overhead backend. This processor
    is intentionally independent so a decoded PCM stream, preview, or future
    audio sink can use the exact same preset math without importing Qt.
    """

    def __init__(self, sample_rate: int = 44100, channels: int = 2, q: float = 1.0):
        self.sample_rate = max(8000, int(sample_rate))
        self.channels = max(1, int(channels))
        self.q = max(0.1, float(q))
        self._states = [[(0.0, 0.0, 0.0, 0.0) for _ in EQ_BANDS_HZ] for _ in range(self.channels)]

    def _coefficients(self, frequency: float, gain: float):
        a = 10.0 ** (gain / 40.0)
        omega = 2.0 * math.pi * frequency / self.sample_rate
        alpha = math.sin(omega) / (2.0 * self.q)
        cos_omega = math.cos(omega)
        b0 = 1.0 + alpha * a
        b1 = -2.0 * cos_omega
        b2 = 1.0 - alpha * a
        a0 = 1.0 + alpha / a
        a1 = -2.0 * cos_omega
        a2 = 1.0 - alpha / a
        return (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)

    def process(self, samples: Sequence[float], gains: Optional[Iterable[float]]) -> List[float]:
        """Process interleaved normalized PCM samples and clip safely."""

        normalized = normalize_gains(gains)
        output = [float(sample) for sample in samples]
        for band_index, (frequency, gain) in enumerate(zip(EQ_BANDS_HZ, normalized)):
            if gain == 0:
                continue
            b0, b1, b2, a1, a2 = self._coefficients(frequency, gain)
            for sample_index, sample in enumerate(output):
                channel = sample_index % self.channels
                x1, x2, y1, y2 = self._states[channel][band_index]
                value = b0 * sample + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
                self._states[channel][band_index] = (sample, x1, value, y1)
                output[sample_index] = max(-1.0, min(1.0, value))
        return [max(-1.0, min(1.0, value)) for value in output]
