"""
Síntesis CS-80 ampliada: doble capa, filtros LP/HP/BP, ring mod,
sub-oscilador, aftertouch, efectos, arpegiador y buffer para osciloscopio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

import numpy as np

from audio_engine import WaveGenerator, midi_to_freq
from effects import EffectChain, EffectParams
from sequencer import ArpMode, Arpeggiator
from step_sequencer import StepSequencer


class LfoWaveform(str, Enum):
    SINE = "sine"
    TRIANGLE = "triangle"
    SQUARE = "square"


class Waveform(str, Enum):
    SAW = "saw"
    SQUARE = "square"
    SINE = "sine"
    NOISE = "noise"
    TRIANGLE = "triangle"


class FilterType(str, Enum):
    LOWPASS = "lowpass"
    HIGHPASS = "highpass"
    BANDPASS = "bandpass"


@dataclass
class EnvelopeParams:
    attack: float = 0.01
    decay: float = 0.2
    sustain: float = 0.7
    release: float = 0.5


@dataclass
class LayerParams:
    osc1_wave: Waveform = Waveform.SAW
    osc2_wave: Waveform = Waveform.SQUARE
    osc_mix: float = 0.5
    detune_cents: float = 0.0
    level: float = 1.0


@dataclass
class SynthParams:
    layer1: LayerParams = field(default_factory=LayerParams)
    layer2: LayerParams = field(default_factory=lambda: LayerParams(
        osc1_wave=Waveform.SINE, osc2_wave=Waveform.SAW, osc_mix=0.4, detune_cents=7.0, level=0.6
    ))
    layer2_enabled: bool = False
    layer2_mix: float = 0.4
    cutoff: float = 3000.0
    resonance: float = 0.4
    filter_type: FilterType = FilterType.LOWPASS
    amp_env: EnvelopeParams = field(default_factory=EnvelopeParams)
    filter_env: EnvelopeParams = field(default_factory=EnvelopeParams)
    filter_env_amount: float = 0.5
    lfo_rate: float = 5.0
    lfo_depth: float = 0.0
    lfo_filter_depth: float = 0.0
    lfo_wave: LfoWaveform = LfoWaveform.SINE
    lfo_tremolo: float = 0.0
    volume: float = 0.5
    pitch_bend: float = 0.0
    ribbon: float = 0.0
    pan: float = 0.0
    portamento: float = 0.0
    unison: float = 0.0
    stereo_width: float = 0.5
    ring_mod_amount: float = 0.0
    sub_osc_level: float = 0.0
    aftertouch_depth: float = 0.0
    effects: EffectParams = field(default_factory=EffectParams)
    arp_enabled: bool = False
    arp_rate: float = 4.0
    arp_mode: ArpMode = ArpMode.UP
    arp_octaves: int = 1
    seq_enabled: bool = False
    seq_bpm: float = 100.0
    seq_swing: float = 0.0

    # Compatibilidad con API anterior
    @property
    def osc1_wave(self) -> Waveform:
        return self.layer1.osc1_wave

    @property
    def osc2_wave(self) -> Waveform:
        return self.layer1.osc2_wave

    @property
    def osc_mix(self) -> float:
        return self.layer1.osc_mix


class ADSR:
    IDLE = 0
    ATTACK = 1
    DECAY = 2
    SUSTAIN = 3
    RELEASE = 4

    def __init__(self, params: EnvelopeParams, sample_rate: int) -> None:
        self.params = params
        self.sample_rate = sample_rate
        self.state = self.IDLE
        self.level = 0.0
        self.note_on_trigger = False

    def trigger(self) -> None:
        self.note_on_trigger = True
        self.state = self.ATTACK

    def release(self) -> None:
        if self.state != self.IDLE:
            self.state = self.RELEASE

    def reset(self) -> None:
        self.state = self.IDLE
        self.level = 0.0

    def _rate(self, seconds: float) -> float:
        if seconds <= 0.0:
            return 1.0
        return 1.0 / (seconds * self.sample_rate)

    def process_block(self, num_samples: int) -> np.ndarray:
        out = np.empty(num_samples, dtype=np.float64)
        attack_rate = self._rate(self.params.attack)
        decay_rate = self._rate(self.params.decay)
        release_rate = self._rate(self.params.release)
        sustain = self.params.sustain

        for i in range(num_samples):
            if self.note_on_trigger:
                self.note_on_trigger = False
                self.state = self.ATTACK

            if self.state == self.IDLE:
                self.level = 0.0
            elif self.state == self.ATTACK:
                self.level += attack_rate
                if self.level >= 1.0:
                    self.level = 1.0
                    self.state = self.DECAY
            elif self.state == self.DECAY:
                self.level -= decay_rate * (1.0 - sustain)
                if self.level <= sustain:
                    self.level = sustain
                    self.state = self.SUSTAIN
            elif self.state == self.SUSTAIN:
                self.level = sustain
            elif self.state == self.RELEASE:
                self.level -= release_rate * self.level
                if self.level <= 1e-6:
                    self.level = 0.0
                    self.state = self.IDLE

            out[i] = self.level

        return out


class StateVariableFilter:
    """Filtro SVF con salidas LP, HP y BP."""

    def __init__(self) -> None:
        self.ic1eq = 0.0
        self.ic2eq = 0.0

    def reset(self) -> None:
        self.ic1eq = 0.0
        self.ic2eq = 0.0

    def process_block(
        self,
        input_samples: np.ndarray,
        cutoff_hz: np.ndarray,
        resonance: float,
        sample_rate: int,
        mode: FilterType = FilterType.LOWPASS,
    ) -> np.ndarray:
        output = np.empty_like(input_samples)
        res = np.clip(resonance, 0.0, 0.99)

        for i, sample in enumerate(input_samples):
            g = np.tan(np.pi * np.clip(cutoff_hz[i], 20.0, sample_rate * 0.45) / sample_rate)
            k = 2.0 - 2.0 * res
            a1 = 1.0 / (1.0 + g * (g + k))
            a2 = g * a1
            a3 = g * a2

            v3 = sample - self.ic2eq
            v1 = a1 * self.ic1eq + a2 * v3
            v2 = self.ic2eq + a2 * self.ic1eq + a3 * v3
            self.ic1eq = 2.0 * v1 - self.ic1eq
            self.ic2eq = 2.0 * v2 - self.ic2eq

            if mode == FilterType.HIGHPASS:
                output[i] = sample - k * v1 - v2
            elif mode == FilterType.BANDPASS:
                output[i] = v1
            else:
                output[i] = v2

        return output


class CS80Voice:
    """Voz con doble capa, ring mod y sub-oscilador."""

    def __init__(self, sample_rate: int = 44100) -> None:
        self.sample_rate = sample_rate
        self.params = SynthParams()
        self.active = False
        self.note: Optional[int] = None
        self.velocity = 0.0
        self.aftertouch = 0.0

        self._phase1 = 0.0
        self._phase2 = 0.0
        self._phase1_b = 0.0
        self._phase2_b = 0.0
        self._sub_phase = 0.0
        self._lfo_phase = 0.0
        self._current_freq = 440.0
        self._target_freq = 440.0
        self._rng = np.random.default_rng()

        self._amp_env = ADSR(self.params.amp_env, sample_rate)
        self._filter_env = ADSR(self.params.filter_env, sample_rate)
        self._filter = StateVariableFilter()

    def apply_params(self, params: SynthParams) -> None:
        self.params = params
        self._amp_env.params = params.amp_env
        self._filter_env.params = params.filter_env

    def set_aftertouch(self, value: float) -> None:
        self.aftertouch = np.clip(value, 0.0, 1.0)

    def note_on(self, note: int, velocity: int = 100) -> None:
        was_active = self.active
        self.active = True
        self.note = note
        self.velocity = np.clip(velocity / 127.0, 0.0, 1.0)
        self.aftertouch = 0.0
        self._target_freq = midi_to_freq(note)
        if self.params.portamento <= 0.0 or not was_active:
            self._current_freq = self._target_freq
            self._phase1 = self._phase2 = 0.0
            self._phase1_b = self._phase2_b = 0.0
        self._sub_phase = 0.0
        self._filter.reset()
        self._amp_env.trigger()
        self._filter_env.trigger()

    def note_off(self, note: Optional[int] = None) -> None:
        if note is not None and self.note != note:
            return
        self._amp_env.release()
        self._filter_env.release()

    def _render_osc(
        self,
        waveform: Waveform,
        phase: float,
        phase_inc,
        num_samples: int,
    ) -> tuple[np.ndarray, float]:
        if np.isscalar(phase_inc):
            t = np.arange(num_samples, dtype=np.float64)
            phases = (phase + t * float(phase_inc)) % 1.0
            new_phase = (phase + num_samples * float(phase_inc)) % 1.0
        else:
            inc = np.asarray(phase_inc, dtype=np.float64)
            if len(inc) != num_samples:
                inc = np.interp(
                    np.linspace(0, 1, num_samples),
                    np.linspace(0, 1, len(inc)),
                    inc,
                )
            phases = (phase + np.concatenate([[0.0], np.cumsum(inc[:-1])])) % 1.0
            new_phase = (phase + float(np.sum(inc))) % 1.0

        if waveform == Waveform.SAW:
            samples = WaveGenerator.saw(phases)
        elif waveform == Waveform.SQUARE:
            samples = WaveGenerator.square(phases)
        elif waveform == Waveform.SINE:
            samples = WaveGenerator.sine(phases)
        elif waveform == Waveform.TRIANGLE:
            samples = 2.0 * np.abs(2.0 * (phases - np.floor(phases + 0.5))) - 1.0
        else:
            samples = WaveGenerator.noise(num_samples, self._rng)

        return samples, new_phase

    def _render_layer(
        self,
        layer: LayerParams,
        phase1: float,
        phase2: float,
        base_phase_inc: float,
        num_samples: int,
    ) -> tuple[np.ndarray, float, float]:
        detune = 2.0 ** (layer.detune_cents / 1200.0)
        inc = base_phase_inc * detune
        o1, p1 = self._render_osc(layer.osc1_wave, phase1, inc, num_samples)
        o2, p2 = self._render_osc(layer.osc2_wave, phase2, inc, num_samples)
        mix = np.clip(layer.osc_mix, 0.0, 1.0)
        return ((1.0 - mix) * o1 + mix * o2) * layer.level, p1, p2

    def _lfo_shape(self, phases: np.ndarray) -> np.ndarray:
        wave = self.params.lfo_wave
        if wave == LfoWaveform.TRIANGLE:
            return 2.0 * np.abs(2.0 * (phases - np.floor(phases + 0.5))) - 1.0
        if wave == LfoWaveform.SQUARE:
            return np.sign(WaveGenerator.sine(phases))
        return WaveGenerator.sine(phases)

    def _glide_freq(self, num_samples: int) -> np.ndarray:
        freqs = np.empty(num_samples, dtype=np.float64)
        port = max(self.params.portamento, 0.0)
        if port <= 0.0:
            freqs.fill(self._target_freq)
            self._current_freq = self._target_freq
            return freqs

        step = (self._target_freq - self._current_freq) / max(port * self.sample_rate, 1.0)
        f = self._current_freq
        for i in range(num_samples):
            if abs(self._target_freq - f) <= abs(step):
                f = self._target_freq
            else:
                f += step
            freqs[i] = f
        self._current_freq = f
        return freqs

    def render(self, num_samples: int) -> np.ndarray:
        if not self.active:
            return np.zeros(num_samples, dtype=np.float64)

        amp_env = self._amp_env.process_block(num_samples)
        filter_env = self._filter_env.process_block(num_samples)

        if self._amp_env.state == ADSR.IDLE and self._amp_env.level <= 0.0:
            self.active = False
            self.note = None
            return np.zeros(num_samples, dtype=np.float64)

        lfo_inc = self.params.lfo_rate / self.sample_rate
        lfo_t = np.arange(num_samples, dtype=np.float64)
        lfo_phases = (self._lfo_phase + lfo_t * lfo_inc) % 1.0
        self._lfo_phase = (self._lfo_phase + num_samples * lfo_inc) % 1.0
        lfo = self._lfo_shape(lfo_phases)

        freq_base = self._glide_freq(num_samples)
        bend = 2.0 ** ((self.params.pitch_bend + self.params.ribbon * 2.0) / 12.0)
        vibrato = 2.0 ** (lfo * self.params.lfo_depth * 0.05)
        freq = freq_base * bend * vibrato
        phase_inc = freq / self.sample_rate

        layer1, self._phase1, self._phase2 = self._render_layer(
            self.params.layer1, self._phase1, self._phase2, phase_inc, num_samples
        )
        raw = layer1

        if self.params.layer2_enabled:
            layer2, self._phase1_b, self._phase2_b = self._render_layer(
                self.params.layer2, self._phase1_b, self._phase2_b, phase_inc, num_samples
            )
            l2mix = np.clip(self.params.layer2_mix, 0.0, 1.0)
            raw = raw * (1.0 - l2mix) + layer2 * l2mix

        if self.params.unison > 0.0:
            det = 1.0 + self.params.unison * 0.008
            u1, _, _ = self._render_layer(
                self.params.layer1, self._phase1, self._phase2, phase_inc * det, num_samples
            )
            raw = raw * (1.0 - 0.35 * self.params.unison) + u1 * 0.35 * self.params.unison

        if self.params.ring_mod_amount > 0.0:
            ring = self._render_osc(Waveform.SINE, 0.0, phase_inc * 2.0, num_samples)[0]
            rm = np.clip(self.params.ring_mod_amount, 0.0, 1.0)
            raw = raw * (1.0 - rm) + (raw * ring) * rm

        if self.params.sub_osc_level > 0.0:
            sub_inc = phase_inc * 0.5
            sub, self._sub_phase = self._render_osc(
                Waveform.SQUARE, self._sub_phase, sub_inc, num_samples
            )
            raw += sub * np.clip(self.params.sub_osc_level, 0.0, 1.0) * 0.5

        at_cutoff_boost = 1.0 + self.aftertouch * self.params.aftertouch_depth * 2.0
        base_cutoff = self.params.cutoff * at_cutoff_boost
        env_amt = self.params.filter_env_amount
        lfo_filt = 1.0 + lfo * self.params.lfo_filter_depth * 0.5
        cutoff = base_cutoff * (1.0 + filter_env * env_amt * 4.0) * lfo_filt
        cutoff = np.clip(cutoff, 20.0, self.sample_rate * 0.45)

        filtered = self._filter.process_block(
            raw, cutoff, self.params.resonance, self.sample_rate, self.params.filter_type
        )

        vel_scale = 0.3 + 0.7 * self.velocity
        tremolo = 1.0 - self.params.lfo_tremolo * (0.5 + 0.5 * lfo)
        return filtered * amp_env * vel_scale * tremolo


class CS80Synth:
    NUM_VOICES = 8
    SCOPE_SIZE = 512
    FFT_SIZE = 256

    def __init__(self, sample_rate: int = 44100) -> None:
        self.sample_rate = sample_rate
        self.params = SynthParams()
        self.voices: List[CS80Voice] = [CS80Voice(sample_rate) for _ in range(self.NUM_VOICES)]
        self.effects = EffectChain(sample_rate)
        self.arpeggiator = Arpeggiator()
        self.step_sequencer = StepSequencer()
        self._voice_index = 0
        self._held_notes: List[int] = []
        self._scope_buffer = np.zeros(self.SCOPE_SIZE, dtype=np.float32)
        self._spectrum_buffer = np.zeros(self.FFT_SIZE // 2, dtype=np.float32)
        self._arp_voice_note: Optional[int] = None
        self._seq_voice_note: Optional[int] = None
        self.global_aftertouch = 0.0

    def apply_params(self, params: Optional[SynthParams] = None) -> None:
        if params is not None:
            self.params = params
        self.effects.params = self.params.effects
        self.arpeggiator.enabled = self.params.arp_enabled
        self.arpeggiator.rate_hz = self.params.arp_rate
        self.arpeggiator.mode = self.params.arp_mode
        self.arpeggiator.octaves = max(1, min(3, self.params.arp_octaves))
        self.step_sequencer.enabled = self.params.seq_enabled
        self.step_sequencer.bpm = self.params.seq_bpm
        self.step_sequencer.swing = self.params.seq_swing
        for voice in self.voices:
            voice.apply_params(self.params)

    def set_ribbon(self, value: float) -> None:
        self.params.ribbon = np.clip(value, -1.0, 1.0)
        for voice in self.voices:
            voice.params.ribbon = self.params.ribbon

    def set_pitch_bend(self, semitones: float) -> None:
        self.params.pitch_bend = np.clip(semitones, -7.0, 7.0)
        for voice in self.voices:
            voice.params.pitch_bend = self.params.pitch_bend

    def set_mod_wheel(self, value: float) -> None:
        self.params.lfo_depth = np.clip(value, 0.0, 1.0)
        for voice in self.voices:
            voice.params.lfo_depth = self.params.lfo_depth

    def set_aftertouch(self, value: float) -> None:
        self.global_aftertouch = np.clip(value / 127.0 if value > 1.0 else value, 0.0, 1.0)
        for voice in self.voices:
            if voice.active:
                voice.set_aftertouch(self.global_aftertouch)

    def note_on(self, note: int, velocity: int = 100) -> None:
        if note not in self._held_notes:
            self._held_notes.append(note)
        self.arpeggiator.set_held_notes(self._held_notes)

        if self.params.arp_enabled:
            return

        if self.params.seq_enabled:
            return

        self._trigger_voice(note, velocity)

    def _trigger_voice(self, note: int, velocity: int) -> None:
        for voice in self.voices:
            if voice.active and voice.note == note:
                voice.note_off(note)

        free = next((v for v in self.voices if not v.active), None)
        if free is None:
            free = self.voices[self._voice_index]
            self._voice_index = (self._voice_index + 1) % self.NUM_VOICES

        free.apply_params(self.params)
        free.note_on(note, velocity)

    def note_off(self, note: int) -> None:
        if note in self._held_notes:
            self._held_notes.remove(note)
        self.arpeggiator.set_held_notes(self._held_notes)

        if self.params.arp_enabled:
            if not self._held_notes:
                if self._arp_voice_note is not None:
                    for voice in self.voices:
                        if voice.active and voice.note == self._arp_voice_note:
                            voice.note_off(self._arp_voice_note)
                    self._arp_voice_note = None
            return

        if self.params.seq_enabled:
            return

        for voice in self.voices:
            if voice.active and voice.note == note:
                voice.note_off(note)

    def all_notes_off(self) -> None:
        self._held_notes.clear()
        self.arpeggiator.set_held_notes([])
        self._arp_voice_note = None
        self._seq_voice_note = None
        for voice in self.voices:
            if voice.active:
                voice.note_off()

    def _process_arpeggiator(self, num_samples: int) -> None:
        if not self.params.arp_enabled:
            return

        note, gate_on, note_off = self.arpeggiator.process(self.sample_rate, num_samples)

        if note_off is not None:
            for voice in self.voices:
                if voice.active and voice.note == note_off:
                    voice.note_off(note_off)
            if self._arp_voice_note == note_off:
                self._arp_voice_note = None

        if gate_on and note is not None and note != self._arp_voice_note:
            if self._arp_voice_note is not None:
                for voice in self.voices:
                    if voice.active and voice.note == self._arp_voice_note:
                        voice.note_off(self._arp_voice_note)
            self._trigger_voice(note, 100)
            self._arp_voice_note = note

    def _process_step_sequencer(self, num_samples: int) -> None:
        if not self.params.seq_enabled:
            return

        note, velocity, gate_on, note_off = self.step_sequencer.process(self.sample_rate, num_samples)

        if note_off is not None:
            for voice in self.voices:
                if voice.active and voice.note == note_off:
                    voice.note_off(note_off)
            if self._seq_voice_note == note_off:
                self._seq_voice_note = None

        if gate_on and note is not None:
            if self._seq_voice_note is not None and self._seq_voice_note != note:
                for voice in self.voices:
                    if voice.active and voice.note == self._seq_voice_note:
                        voice.note_off(self._seq_voice_note)
            self._trigger_voice(note, velocity)
            self._seq_voice_note = note

    def get_spectrum_buffer(self) -> np.ndarray:
        return self._spectrum_buffer.copy()

    def get_scope_buffer(self) -> np.ndarray:
        return self._scope_buffer.copy()

    def _to_stereo(self, mono: np.ndarray) -> np.ndarray:
        pan = np.clip(self.params.pan, -1.0, 1.0)
        width = np.clip(self.params.stereo_width, 0.0, 1.0)
        left = np.sqrt(0.5 * (1.0 - pan)) * width + (1.0 - width)
        right = np.sqrt(0.5 * (1.0 + pan)) * width + (1.0 - width)
        norm = max(left + right, 1.0)
        left /= norm
        right /= norm
        stereo = np.column_stack((mono * left, mono * right))
        return np.clip(stereo, -1.0, 1.0).astype(np.float32)

    def render(self, num_samples: int, stereo: bool = True) -> np.ndarray:
        self._process_arpeggiator(num_samples)
        self._process_step_sequencer(num_samples)

        mix = np.zeros(num_samples, dtype=np.float64)
        for voice in self.voices:
            mix += voice.render(num_samples)

        mix *= self.params.volume
        mix = self.effects.process(mix)
        mix = np.clip(mix, -1.0, 1.0)

        mono = mix.astype(np.float32)
        n = min(num_samples, self.SCOPE_SIZE)
        self._scope_buffer = np.roll(self._scope_buffer, -n)
        self._scope_buffer[-n:] = mono[:n]

        fft_n = min(self.FFT_SIZE, len(mono))
        if fft_n >= 32:
            window = np.hanning(fft_n)
            spec = np.abs(np.fft.rfft(mono[-fft_n:] * window))
            spec = spec / max(float(np.max(spec)), 1e-6)
            bins = min(len(spec), len(self._spectrum_buffer))
            self._spectrum_buffer[:bins] = spec[:bins]

        if stereo:
            return self._to_stereo(mono)
        return mono

    def render_offline(self, num_samples: int, note_events: list[tuple[int, str, int]]) -> np.ndarray:
        """Renderiza offline para exportación (eventos: (sample, 'on'|'off', note))."""
        self.all_notes_off()
        for voice in self.voices:
            voice._filter.reset()
            voice._amp_env.reset()
            voice._filter_env.reset()

        chunks = []
        pos = 0
        event_idx = 0
        block = 512

        while pos < num_samples:
            while event_idx < len(note_events) and note_events[event_idx][0] <= pos:
                _, action, note = note_events[event_idx]
                if action == "on":
                    self._trigger_voice(note, 100)
                else:
                    for voice in self.voices:
                        if voice.active and voice.note == note:
                            voice.note_off(note)
                event_idx += 1

            n = min(block, num_samples - pos)
            chunks.append(self.render(n, stereo=False))
            pos += n

        return np.concatenate(chunks)


def test_polyphony(duration: float = 4.0) -> None:
    import sounddevice as sd
    from audio_engine import AudioEngine, BLOCK_SIZE

    synth = CS80Synth()
    synth.apply_params(SynthParams())

    chord = [60, 64, 67, 72]
    step = 0
    samples_elapsed = 0
    note_interval = int(0.5 * synth.sample_rate)
    total_samples = int(duration * synth.sample_rate)

    def callback(frames: int) -> np.ndarray:
        nonlocal step, samples_elapsed
        if samples_elapsed % note_interval == 0 and samples_elapsed < total_samples // 2:
            synth.note_on(chord[step % len(chord)], 90)
            step += 1
        if samples_elapsed == total_samples // 2:
            synth.all_notes_off()
        samples_elapsed += frames
        return synth.render(frames, stereo=False)

    engine = AudioEngine(block_size=BLOCK_SIZE)
    print("[CS80Synth] Prueba de polifonía...")
    engine.start(callback)
    sd.sleep(int(duration * 1000))
    engine.stop()
    print("[CS80Synth] Prueba completada.")


if __name__ == "__main__":
    test_polyphony()
