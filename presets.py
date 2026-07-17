"""
Presets Blade Runner / Vangelis ampliados.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, List

from effects import EffectParams
from sequencer import ArpMode
from synth_voice import CS80Synth, EnvelopeParams, FilterType, LayerParams, LfoWaveform, SynthParams, Waveform


def _lead_vangelis() -> SynthParams:
    return SynthParams(
        layer1=LayerParams(Waveform.SAW, Waveform.SQUARE, 0.35),
        layer2=LayerParams(Waveform.SINE, Waveform.SAW, 0.5, detune_cents=12.0, level=0.5),
        layer2_enabled=True,
        layer2_mix=0.3,
        cutoff=4200.0,
        resonance=0.55,
        filter_type=FilterType.LOWPASS,
        amp_env=EnvelopeParams(0.08, 0.3, 0.75, 0.8),
        filter_env=EnvelopeParams(0.05, 0.4, 0.4, 0.6),
        filter_env_amount=0.65,
        lfo_rate=4.5,
        lfo_depth=0.15,
        lfo_filter_depth=0.1,
        volume=0.55,
        effects=EffectParams(delay_mix=0.15, delay_time=0.28, reverb_mix=0.25, chorus_mix=0.1),
    )


def _pad_atmosferico() -> SynthParams:
    return SynthParams(
        layer1=LayerParams(Waveform.SAW, Waveform.SINE, 0.6),
        layer2=LayerParams(Waveform.SINE, Waveform.TRIANGLE, 0.7, detune_cents=-8.0, level=0.7),
        layer2_enabled=True,
        layer2_mix=0.55,
        cutoff=1800.0,
        resonance=0.25,
        amp_env=EnvelopeParams(1.2, 0.8, 0.85, 2.5),
        filter_env=EnvelopeParams(0.9, 1.0, 0.5, 2.0),
        filter_env_amount=0.4,
        lfo_rate=0.25,
        lfo_depth=0.08,
        lfo_filter_depth=0.2,
        volume=0.45,
        effects=EffectParams(reverb_mix=0.55, reverb_size=0.8, chorus_mix=0.25, delay_mix=0.1),
    )


def _brass_futurista() -> SynthParams:
    return SynthParams(
        layer1=LayerParams(Waveform.SAW, Waveform.SAW, 0.5),
        cutoff=2800.0,
        resonance=0.7,
        filter_env_amount=0.8,
        amp_env=EnvelopeParams(0.02, 0.15, 0.6, 0.4),
        filter_env=EnvelopeParams(0.01, 0.2, 0.3, 0.35),
        lfo_rate=6.0,
        lfo_depth=0.05,
        sub_osc_level=0.2,
        volume=0.6,
        effects=EffectParams(chorus_mix=0.15),
    )


def _lluvia_neon() -> SynthParams:
    return SynthParams(
        layer1=LayerParams(Waveform.NOISE, Waveform.SINE, 0.2),
        cutoff=900.0,
        resonance=0.45,
        filter_type=FilterType.BANDPASS,
        amp_env=EnvelopeParams(0.5, 0.5, 0.7, 1.5),
        filter_env=EnvelopeParams(0.3, 0.6, 0.5, 1.2),
        lfo_rate=0.1,
        lfo_depth=0.02,
        volume=0.35,
        effects=EffectParams(reverb_mix=0.6, delay_mix=0.3, delay_time=0.45),
    )


PRESETS: Dict[str, SynthParams] = {
    "Lead Vangelis": _lead_vangelis(),
    "Pad Atmosferico": _pad_atmosferico(),
    "Brass Futurista": _brass_futurista(),
    "Lluvia Neon": _lluvia_neon(),
    "Tears In Rain": SynthParams(
        layer1=LayerParams(Waveform.SINE, Waveform.TRIANGLE, 0.55),
        layer2=LayerParams(Waveform.SAW, Waveform.SINE, 0.4, detune_cents=5.0),
        layer2_enabled=True,
        layer2_mix=0.45,
        cutoff=2200.0,
        resonance=0.35,
        amp_env=EnvelopeParams(1.5, 1.0, 0.8, 3.0),
        filter_env=EnvelopeParams(1.2, 0.8, 0.4, 2.5),
        lfo_rate=0.18,
        lfo_depth=0.12,
        lfo_filter_depth=0.35,
        volume=0.4,
        effects=EffectParams(reverb_mix=0.7, reverb_size=0.9, delay_mix=0.2, chorus_mix=0.3),
    ),
    "Flying Theme": SynthParams(
        layer1=LayerParams(Waveform.SAW, Waveform.SQUARE, 0.4),
        layer2=LayerParams(Waveform.SAW, Waveform.SAW, 0.5, detune_cents=15.0),
        layer2_enabled=True,
        layer2_mix=0.5,
        cutoff=5000.0,
        resonance=0.5,
        ring_mod_amount=0.08,
        amp_env=EnvelopeParams(0.3, 0.5, 0.7, 1.2),
        filter_env=EnvelopeParams(0.2, 0.6, 0.5, 0.8),
        lfo_rate=5.5,
        lfo_depth=0.2,
        volume=0.5,
        arp_enabled=True,
        arp_rate=6.0,
        arp_mode=ArpMode.UP,
        arp_octaves=2,
        effects=EffectParams(delay_mix=0.25, reverb_mix=0.35, chorus_mix=0.2),
    ),
    "Replicant Bass": SynthParams(
        layer1=LayerParams(Waveform.SAW, Waveform.SQUARE, 0.6),
        cutoff=600.0,
        resonance=0.55,
        filter_type=FilterType.LOWPASS,
        sub_osc_level=0.6,
        amp_env=EnvelopeParams(0.005, 0.2, 0.8, 0.3),
        filter_env=EnvelopeParams(0.01, 0.3, 0.2, 0.25),
        filter_env_amount=0.9,
        volume=0.65,
        effects=EffectParams(chorus_mix=0.1, delay_mix=0.05),
    ),
    "Voight-Kampff": SynthParams(
        layer1=LayerParams(Waveform.SQUARE, Waveform.NOISE, 0.3),
        cutoff=3500.0,
        resonance=0.8,
        filter_type=FilterType.HIGHPASS,
        ring_mod_amount=0.35,
        amp_env=EnvelopeParams(0.01, 0.1, 0.5, 0.2),
        filter_env=EnvelopeParams(0.005, 0.15, 0.2, 0.15),
        filter_env_amount=1.0,
        lfo_rate=8.0,
        lfo_depth=0.4,
        lfo_filter_depth=0.5,
        aftertouch_depth=0.8,
        volume=0.5,
        effects=EffectParams(delay_mix=0.15, reverb_mix=0.2),
    ),
    "Tyrell Corp": SynthParams(
        layer1=LayerParams(Waveform.SINE, Waveform.TRIANGLE, 0.5),
        layer2=LayerParams(Waveform.SAW, Waveform.SINE, 0.45, detune_cents=19.0),
        layer2_enabled=True,
        layer2_mix=0.35,
        cutoff=3200.0,
        resonance=0.4,
        portamento=0.08,
        lfo_rate=0.35,
        lfo_depth=0.1,
        lfo_tremolo=0.15,
        volume=0.42,
        effects=EffectParams(reverb_mix=0.65, chorus_mix=0.35, delay_mix=0.12),
    ),
    "Spinner Over LA": SynthParams(
        layer1=LayerParams(Waveform.SAW, Waveform.SAW, 0.5, detune_cents=5.0),
        cutoff=1400.0,
        resonance=0.6,
        sub_osc_level=0.45,
        seq_enabled=True,
        seq_bpm=92.0,
        unison=0.3,
        stereo_width=0.9,
        pan=0.15,
        volume=0.58,
        effects=EffectParams(reverb_mix=0.45, delay_mix=0.22, bitcrush_bits=12, bitcrush_mix=0.08),
    ),
    "Pris Attack": SynthParams(
        layer1=LayerParams(Waveform.SQUARE, Waveform.SAW, 0.4),
        cutoff=6500.0,
        resonance=0.85,
        filter_type=FilterType.HIGHPASS,
        ring_mod_amount=0.5,
        amp_env=EnvelopeParams(0.001, 0.05, 0.4, 0.15),
        lfo_rate=12.0,
        lfo_depth=0.55,
        lfo_wave=LfoWaveform.SQUARE,
        volume=0.55,
        effects=EffectParams(delay_mix=0.08, bitcrush_bits=8, bitcrush_mix=0.15),
    ),
    "Unicorn Dream": SynthParams(
        layer1=LayerParams(Waveform.SINE, Waveform.SINE, 0.55),
        layer2=LayerParams(Waveform.TRIANGLE, Waveform.SINE, 0.6, detune_cents=-12.0),
        layer2_enabled=True,
        layer2_mix=0.5,
        cutoff=2600.0,
        resonance=0.3,
        portamento=0.2,
        ribbon=0.0,
        lfo_rate=0.15,
        lfo_filter_depth=0.45,
        volume=0.38,
        effects=EffectParams(reverb_mix=0.75, reverb_size=0.95, chorus_mix=0.4),
    ),
}


def list_presets() -> List[str]:
    return list(PRESETS.keys())


def get_preset(name: str) -> SynthParams:
    if name not in PRESETS:
        raise KeyError(f"Preset desconocido: {name}. Disponibles: {list_presets()}")
    return deepcopy(PRESETS[name])


def load_preset(name: str, synth_instance: CS80Synth) -> SynthParams:
    params = get_preset(name)
    synth_instance.apply_params(params)
    return params
