"""
Generador de parches aleatorios estilo Blade Runner.
"""

from __future__ import annotations

import random

from effects import EffectParams
from sequencer import ArpMode
from synth_voice import EnvelopeParams, FilterType, LayerParams, LfoWaveform, SynthParams, Waveform


def random_patch(seed: int | None = None) -> SynthParams:
    rng = random.Random(seed)

    waves = list(Waveform)
    filt = rng.choice(list(FilterType))

    return SynthParams(
        layer1=LayerParams(
            rng.choice(waves), rng.choice(waves), rng.uniform(0.2, 0.8),
            rng.uniform(-15, 15), rng.uniform(0.6, 1.0),
        ),
        layer2=LayerParams(
            rng.choice(waves), rng.choice(waves), rng.uniform(0.3, 0.7),
            rng.uniform(-25, 25), rng.uniform(0.4, 0.9),
        ),
        layer2_enabled=rng.random() > 0.4,
        layer2_mix=rng.uniform(0.2, 0.6),
        cutoff=rng.uniform(400, 7000),
        resonance=rng.uniform(0.1, 0.85),
        filter_type=filt,
        amp_env=EnvelopeParams(
            rng.uniform(0.005, 0.5), rng.uniform(0.05, 1.0),
            rng.uniform(0.3, 0.9), rng.uniform(0.1, 2.5),
        ),
        filter_env=EnvelopeParams(
            rng.uniform(0.005, 0.4), rng.uniform(0.05, 0.8),
            rng.uniform(0.2, 0.7), rng.uniform(0.1, 2.0),
        ),
        filter_env_amount=rng.uniform(0.2, 1.0),
        lfo_rate=rng.uniform(0.1, 10),
        lfo_depth=rng.uniform(0, 0.4),
        lfo_filter_depth=rng.uniform(0, 0.5),
        lfo_wave=rng.choice(list(LfoWaveform)),
        lfo_tremolo=rng.uniform(0, 0.3),
        volume=rng.uniform(0.35, 0.65),
        ring_mod_amount=rng.uniform(0, 0.4) if rng.random() > 0.7 else 0,
        sub_osc_level=rng.uniform(0, 0.5) if rng.random() > 0.5 else 0,
        portamento=rng.uniform(0, 0.15) if rng.random() > 0.6 else 0,
        unison=rng.uniform(0, 0.4) if rng.random() > 0.65 else 0,
        pan=rng.uniform(-0.5, 0.5),
        stereo_width=rng.uniform(0.3, 1.0),
        effects=EffectParams(
            delay_time=rng.uniform(0.1, 0.6),
            delay_feedback=rng.uniform(0.1, 0.6),
            delay_mix=rng.uniform(0, 0.4),
            reverb_size=rng.uniform(0.3, 0.95),
            reverb_mix=rng.uniform(0, 0.6),
            chorus_rate=rng.uniform(0.2, 2.0),
            chorus_depth=rng.uniform(0.001, 0.008),
            chorus_mix=rng.uniform(0, 0.35),
            bitcrush_bits=rng.choice([16, 16, 12, 10, 8]),
            bitcrush_mix=rng.uniform(0, 0.2) if rng.random() > 0.8 else 0,
        ),
        arp_enabled=rng.random() > 0.75,
        arp_rate=rng.uniform(2, 10),
        arp_mode=rng.choice(list(ArpMode)),
        arp_octaves=rng.randint(1, 2),
    )
