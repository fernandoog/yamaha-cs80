"""
Cadena de efectos post-síntesis: delay, reverb, chorus.
Inspirado en cadenas de estudio ochenteras / Vangelis.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class EffectParams:
    delay_time: float = 0.35
    delay_feedback: float = 0.35
    delay_mix: float = 0.0
    reverb_size: float = 0.6
    reverb_mix: float = 0.0
    chorus_rate: float = 0.8
    chorus_depth: float = 0.003
    chorus_mix: float = 0.0
    bitcrush_bits: float = 16.0
    bitcrush_mix: float = 0.0


class DelayEffect:
    """Delay simple con feedback."""

    def __init__(self, sample_rate: int, max_time: float = 2.0) -> None:
        self.sample_rate = sample_rate
        self.max_samples = int(max_time * sample_rate)
        self.buffer = np.zeros(self.max_samples, dtype=np.float64)
        self.write_pos = 0
        self.feedback = 0.0

    def process(self, samples: np.ndarray, time_sec: float, feedback: float, mix: float) -> np.ndarray:
        if mix <= 0.0:
            return samples

        delay_samples = int(np.clip(time_sec, 0.001, 1.99) * self.sample_rate)
        out = np.empty_like(samples)
        fb = np.clip(feedback, 0.0, 0.95)

        for i, sample in enumerate(samples):
            read_pos = (self.write_pos - delay_samples) % self.max_samples
            delayed = self.buffer[read_pos]
            wet = sample + delayed * fb
            self.buffer[self.write_pos] = wet
            self.write_pos = (self.write_pos + 1) % self.max_samples
            out[i] = sample * (1.0 - mix) + delayed * mix

        return out


class ReverbEffect:
    """Reverb algorítmico (comb filters + allpass)."""

    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self._comb_delays = [1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617]
        self._comb_bufs = [np.zeros(d, dtype=np.float64) for d in self._comb_delays]
        self._comb_idx = [0] * len(self._comb_delays)
        self._ap_delays = [556, 441]
        self._ap_bufs = [np.zeros(d, dtype=np.float64) for d in self._ap_delays]
        self._ap_idx = [0, 0]

    def process(self, samples: np.ndarray, size: float, mix: float) -> np.ndarray:
        if mix <= 0.0:
            return samples

        out = np.empty_like(samples)
        damp = np.clip(size, 0.1, 0.99)

        for i, sample in enumerate(samples):
            comb_sum = 0.0
            for j, delay in enumerate(self._comb_delays):
                idx = self._comb_idx[j]
                buf = self._comb_bufs[j]
                delayed = buf[idx]
                filtered = delayed * damp
                buf[idx] = sample + filtered * 0.84
                self._comb_idx[j] = (idx + 1) % delay
                comb_sum += delayed

            reverb = comb_sum * 0.125
            for j, delay in enumerate(self._ap_delays):
                idx = self._ap_idx[j]
                buf = self._ap_bufs[j]
                delayed = buf[idx]
                v = reverb + delayed * 0.5
                buf[idx] = v
                self._ap_idx[j] = (idx + 1) % delay
                reverb = delayed - v * 0.5

            out[i] = sample * (1.0 - mix) + reverb * mix

        return out


class ChorusEffect:
    """Chorus con LFO modulando retardo corto."""

    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self.max_samples = int(0.05 * sample_rate)
        self.buffer = np.zeros(self.max_samples, dtype=np.float64)
        self.write_pos = 0
        self.lfo_phase = 0.0

    def process(
        self,
        samples: np.ndarray,
        rate: float,
        depth: float,
        mix: float,
    ) -> np.ndarray:
        if mix <= 0.0:
            return samples

        out = np.empty_like(samples)
        base_delay = int(0.02 * self.sample_rate)

        for i, sample in enumerate(samples):
            self.lfo_phase = (self.lfo_phase + rate / self.sample_rate) % 1.0
            lfo = np.sin(2.0 * np.pi * self.lfo_phase)
            delay = int(base_delay + lfo * depth * self.sample_rate)
            delay = np.clip(delay, 1, self.max_samples - 1)

            read_pos = (self.write_pos - delay) % self.max_samples
            self.buffer[self.write_pos] = sample
            self.write_pos = (self.write_pos + 1) % self.max_samples
            chorused = self.buffer[read_pos]
            out[i] = sample * (1.0 - mix) + chorused * mix

        return out


class EffectChain:
    """Cadena: bitcrush → chorus → delay → reverb."""

    def __init__(self, sample_rate: int) -> None:
        self.chorus = ChorusEffect(sample_rate)
        self.delay = DelayEffect(sample_rate)
        self.reverb = ReverbEffect(sample_rate)
        self.params = EffectParams()
        self.quality_depth = 1.0

    @staticmethod
    def _bitcrush(samples: np.ndarray, bits: float, mix: float) -> np.ndarray:
        if mix <= 0.0 or bits >= 16.0:
            return samples
        levels = max(2.0, 2.0 ** np.clip(bits, 4.0, 16.0))
        crushed = np.round(samples * levels) / levels
        return samples * (1.0 - mix) + crushed * mix

    def process(self, samples: np.ndarray) -> np.ndarray:
        p = self.params
        depth = np.clip(self.quality_depth, 0.3, 1.0)
        dry = samples.astype(np.float64, copy=False)
        wet = self._bitcrush(dry, p.bitcrush_bits, p.bitcrush_mix)
        wet = self.chorus.process(wet, p.chorus_rate, p.chorus_depth, p.chorus_mix * depth)
        wet = self.delay.process(wet, p.delay_time, p.delay_feedback, p.delay_mix * depth)
        wet = self.reverb.process(wet, p.reverb_size, p.reverb_mix * depth)
        return np.clip(wet, -1.0, 1.0)
