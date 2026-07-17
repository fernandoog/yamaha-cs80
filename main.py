"""
Script principal — CS-80 Blade Runner Edition v3
Ejecución: python main.py
"""

from __future__ import annotations

import argparse
import sys

from audio_engine import AudioEngine, BLOCK_SIZE, SAMPLE_RATE
from gui import launch_gui
from midi_input import try_start_midi
from presets import load_preset, list_presets
from step_sequencer import BLADE_RUNNER_PATTERNS
from synth_voice import CS80Synth
from wav_export import AudioRecorder


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulador Yamaha CS-80 — Blade Runner v3")
    parser.add_argument("--midi-port", type=str, default=None, help="Puerto MIDI de entrada")
    parser.add_argument("--list-devices", action="store_true", help="Lista dispositivos audio/MIDI")
    parser.add_argument("--test-poly", action="store_true", help="Prueba polifonía sin GUI")
    parser.add_argument("--export-demo", type=str, default=None, metavar="FILE.wav", help="Exporta demo a WAV")
    parser.add_argument("--export-seq", type=str, default=None, metavar="FILE.wav", help="Exporta patrón secuenciador a WAV")
    parser.add_argument("--list-patterns", action="store_true", help="Lista patrones del secuenciador")
    return parser.parse_args()


def export_demo_wav(path: str) -> None:
    from presets import get_preset

    synth = CS80Synth(SAMPLE_RATE)
    synth.apply_params(get_preset("Lead Vangelis"))
    duration = 6.0
    sr = synth.sample_rate
    events = [
        (0, "on", 57), (int(0.5 * sr), "on", 60), (int(1.0 * sr), "on", 64),
        (int(1.5 * sr), "on", 67), (int(3.0 * sr), "off", 57), (int(3.0 * sr), "off", 60),
        (int(3.0 * sr), "off", 64), (int(3.0 * sr), "off", 67),
        (int(3.5 * sr), "on", 72), (int(4.0 * sr), "on", 76), (int(5.0 * sr), "off", 72),
        (int(5.0 * sr), "off", 76),
    ]
    buffer = synth.render_offline(int(duration * sr), events)
    recorder = AudioRecorder(SAMPLE_RATE)
    recorder._chunks = [buffer]
    print(f"[Export] Demo guardada en: {recorder.export_wav(path)}")


def export_seq_wav(path: str, pattern_name: str = "BR Main Theme") -> None:
    from presets import get_preset

    synth = CS80Synth(SAMPLE_RATE)
    synth.apply_params(get_preset("Flying Theme"))
    if pattern_name in BLADE_RUNNER_PATTERNS:
        synth.step_sequencer.set_pattern(BLADE_RUNNER_PATTERNS[pattern_name])
    synth.params.seq_enabled = True
    synth.step_sequencer.enabled = True
    synth.step_sequencer.bpm = 100.0
    bars = 4
    duration = bars * 4 * (60.0 / synth.step_sequencer.bpm)
    buffer = synth.render_offline(int(duration * SAMPLE_RATE), [])
    recorder = AudioRecorder(SAMPLE_RATE)
    recorder._chunks = [buffer]
    print(f"[Export] Secuencia '{pattern_name}' -> {recorder.export_wav(path)}")


def main() -> int:
    args = parse_args()

    print("=" * 60)
    print("  YAMAHA CS-80 SIMULATOR v3  |  BLADE RUNNER EDITION")
    print("=" * 60)

    if args.list_devices:
        print("\n[Dispositivos de audio]")
        AudioEngine.list_devices()
        from midi_input import MIDIInputHandler
        print("\n[Dispositivos MIDI]")
        for port in MIDIInputHandler.list_ports():
            print(f"  - {port}")
        return 0

    if args.list_patterns:
        print("\n[Patrones secuenciador]")
        for name in BLADE_RUNNER_PATTERNS:
            print(f"  - {name}")
        return 0

    if args.test_poly:
        from synth_voice import test_polyphony
        test_polyphony()
        return 0

    if args.export_demo:
        export_demo_wav(args.export_demo)
        return 0

    if args.export_seq:
        export_seq_wav(args.export_seq)
        return 0

    engine = AudioEngine(SAMPLE_RATE, BLOCK_SIZE, channels=2)
    synth = CS80Synth(SAMPLE_RATE)
    recorder = AudioRecorder(SAMPLE_RATE)
    load_preset(list_presets()[0], synth)

    midi_handler = try_start_midi(
        on_note_on=synth.note_on,
        on_note_off=synth.note_off,
        on_pitch_bend=synth.set_pitch_bend,
        on_mod_wheel=synth.set_mod_wheel,
        on_aftertouch=synth.set_aftertouch,
        port_name=args.midi_port,
    )

    def on_close() -> None:
        if midi_handler is not None:
            midi_handler.stop()
        if recorder.recording:
            recorder.stop()
        engine.stop()
        synth.all_notes_off()
        print("[Main] Cierre limpio.")

    print("\n[Main] v3 — SEQ 16 pasos | Estéreo | Portamento | Spectrum | 12 presets")
    print("[Main] Teclado: Z-M + Q-I  |  python main.py --export-seq out.wav\n")

    try:
        launch_gui(synth, engine, recorder, on_close=on_close)
    except KeyboardInterrupt:
        on_close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
