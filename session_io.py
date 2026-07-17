"""
Guardar / cargar sesiones completas (synth + secuenciador + patrón).
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from effects import EffectParams
from sequencer import ArpMode
from step_sequencer import BLADE_RUNNER_PATTERNS, Step, StepPattern, StepSequencer
from synth_voice import CS80Synth, EnvelopeParams, FilterType, LayerParams, LfoWaveform, SynthParams, Waveform


def _enum_val(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _enum_val(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [_enum_val(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _enum_val(v) for k, v in obj.items()}
    return obj


def synth_to_dict(params: SynthParams) -> dict:
    return _enum_val(params)


def dict_to_synth(data: dict) -> SynthParams:
    effects = data.get("effects", {})
    return SynthParams(
        layer1=LayerParams(
            Waveform(data.get("layer1", {}).get("osc1_wave", data.get("layer1_osc1", "saw"))),
            Waveform(data.get("layer1", {}).get("osc2_wave", data.get("layer1_osc2", "square"))),
            float(data.get("layer1", {}).get("osc_mix", data.get("osc_mix", 0.5))),
            float(data.get("layer1", {}).get("detune_cents", 0)),
            float(data.get("layer1", {}).get("level", 1.0)),
        ),
        layer2=LayerParams(
            Waveform(data.get("layer2", {}).get("osc1_wave", data.get("l2_osc1", "sine"))),
            Waveform(data.get("layer2", {}).get("osc2_wave", data.get("l2_osc2", "saw"))),
            float(data.get("layer2", {}).get("osc_mix", data.get("l2_osc_mix", 0.5))),
            float(data.get("layer2", {}).get("detune_cents", data.get("l2_detune", 7))),
            float(data.get("layer2", {}).get("level", data.get("l2_level", 0.6))),
        ),
        layer2_enabled=bool(data.get("layer2_enabled", False)),
        layer2_mix=float(data.get("layer2_mix", 0.4)),
        cutoff=float(data.get("cutoff", 3000)),
        resonance=float(data.get("resonance", 0.4)),
        filter_type=FilterType(data.get("filter_type", "lowpass")),
        amp_env=EnvelopeParams(
            float(data.get("amp_attack", data.get("amp_env", {}).get("attack", 0.01))),
            float(data.get("amp_decay", data.get("amp_env", {}).get("decay", 0.2))),
            float(data.get("amp_sustain", data.get("amp_env", {}).get("sustain", 0.7))),
            float(data.get("amp_release", data.get("amp_env", {}).get("release", 0.5))),
        ),
        filter_env=EnvelopeParams(
            float(data.get("filt_attack", data.get("filter_env", {}).get("attack", 0.01))),
            float(data.get("filt_decay", data.get("filter_env", {}).get("decay", 0.2))),
            float(data.get("filt_sustain", data.get("filter_env", {}).get("sustain", 0.5))),
            float(data.get("filt_release", data.get("filter_env", {}).get("release", 0.5))),
        ),
        filter_env_amount=float(data.get("filter_env_amount", 0.5)),
        lfo_rate=float(data.get("lfo_rate", 5)),
        lfo_depth=float(data.get("lfo_depth", 0)),
        lfo_filter_depth=float(data.get("lfo_filter_depth", 0)),
        lfo_wave=LfoWaveform(data.get("lfo_wave", "sine")),
        lfo_tremolo=float(data.get("lfo_tremolo", 0)),
        volume=float(data.get("volume", 0.5)),
        pitch_bend=float(data.get("pitch_bend", 0)),
        ribbon=float(data.get("ribbon", 0)),
        pan=float(data.get("pan", 0)),
        portamento=float(data.get("portamento", 0)),
        unison=float(data.get("unison", 0)),
        stereo_width=float(data.get("stereo_width", 0.5)),
        ring_mod_amount=float(data.get("ring_mod", data.get("ring_mod_amount", 0))),
        sub_osc_level=float(data.get("sub_osc", data.get("sub_osc_level", 0))),
        aftertouch_depth=float(data.get("aftertouch", data.get("aftertouch_depth", 0))),
        effects=EffectParams(
            float(effects.get("delay_time", data.get("delay_time", 0.35))),
            float(effects.get("delay_feedback", data.get("delay_fb", 0.35))),
            float(effects.get("delay_mix", data.get("delay_mix", 0))),
            float(effects.get("reverb_size", data.get("reverb_size", 0.6))),
            float(effects.get("reverb_mix", data.get("reverb_mix", 0))),
            float(effects.get("chorus_rate", data.get("chorus_rate", 0.8))),
            float(effects.get("chorus_depth", data.get("chorus_depth", 0.003))),
            float(effects.get("chorus_mix", data.get("chorus_mix", 0))),
            float(effects.get("bitcrush_bits", data.get("bitcrush_bits", 16))),
            float(effects.get("bitcrush_mix", data.get("bitcrush_mix", 0))),
        ),
        arp_enabled=bool(data.get("arp_enabled", False)),
        arp_rate=float(data.get("arp_rate", 4)),
        arp_mode=ArpMode(data.get("arp_mode", "up")),
        arp_octaves=int(data.get("arp_octaves", 1)),
        seq_enabled=bool(data.get("seq_enabled", False)),
        seq_bpm=float(data.get("seq_bpm", 100)),
        seq_swing=float(data.get("seq_swing", 0)),
    )


def pattern_to_dict(pattern: StepPattern) -> dict:
    return {
        "name": pattern.name,
        "steps": [
            {"note": s.note, "velocity": s.velocity, "enabled": s.enabled, "accent": s.accent}
            for s in pattern.steps
        ],
    }


def dict_to_pattern(data: dict) -> StepPattern:
    steps = [
        Step(
            note=int(s.get("note", 60)),
            velocity=int(s.get("velocity", 100)),
            enabled=bool(s.get("enabled", True)),
            accent=bool(s.get("accent", False)),
        )
        for s in data.get("steps", [{}] * 16)
    ]
    while len(steps) < 16:
        steps.append(Step(note=-1, enabled=False))
    return StepPattern(name=data.get("name", "Imported"), steps=steps[:16])


def save_session(path: str | Path, synth: CS80Synth, preset_name: str = "") -> Path:
    path = Path(path)
    data = {
        "version": 3,
        "preset_name": preset_name,
        "synth": synth_to_dict(synth.params),
        "sequencer": {
            "enabled": synth.step_sequencer.enabled,
            "bpm": synth.step_sequencer.bpm,
            "swing": synth.step_sequencer.swing,
            "pattern": pattern_to_dict(synth.step_sequencer.pattern),
        },
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load_session(path: str | Path, synth: CS80Synth) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    params = dict_to_synth(data.get("synth", {}))
    synth.apply_params(params)

    seq_data = data.get("sequencer", {})
    synth.step_sequencer.enabled = bool(seq_data.get("enabled", False))
    synth.step_sequencer.bpm = float(seq_data.get("bpm", 100))
    synth.step_sequencer.swing = float(seq_data.get("swing", 0))
    if "pattern" in seq_data:
        synth.step_sequencer.set_pattern(dict_to_pattern(seq_data["pattern"]))

    return data


def list_builtin_patterns() -> list[str]:
    return list(BLADE_RUNNER_PATTERNS.keys())
