"""
Entrada MIDI ampliada: pitch bend, mod wheel, aftertouch, sustain.
"""

from __future__ import annotations

from typing import Callable, List, Optional

try:
    import mido
    MIDI_AVAILABLE = True
except ImportError:
    MIDI_AVAILABLE = False
    mido = None  # type: ignore


class MIDIInputHandler:
    """Escucha mensajes MIDI y los reenvía al sintetizador."""

    def __init__(
        self,
        on_note_on: Callable[[int, int], None],
        on_note_off: Callable[[int], None],
        on_pitch_bend: Optional[Callable[[float], None]] = None,
        on_mod_wheel: Optional[Callable[[float], None]] = None,
        on_aftertouch: Optional[Callable[[float], None]] = None,
        port_name: Optional[str] = None,
    ) -> None:
        if not MIDI_AVAILABLE:
            raise RuntimeError(
                "MIDI no disponible. Instala: pip install mido python-rtmidi"
            )
        self.on_note_on = on_note_on
        self.on_note_off = on_note_off
        self.on_pitch_bend = on_pitch_bend
        self.on_mod_wheel = on_mod_wheel
        self.on_aftertouch = on_aftertouch
        self.port_name = port_name
        self._port = None
        self._running = False

    @staticmethod
    def list_ports() -> List[str]:
        if not MIDI_AVAILABLE:
            return []
        return mido.get_input_names()

    def start(self) -> None:
        if self._running:
            return

        ports = self.list_ports()
        if not ports:
            print("[MIDI] No se encontraron dispositivos MIDI de entrada.")
            return

        name = self.port_name or ports[0]
        print(f"[MIDI] Conectando a: {name}")
        self._port = mido.open_input(name, callback=self._handle_message)
        self._running = True

    def _handle_message(self, msg) -> None:
        if msg.type == "note_on":
            if msg.velocity > 0:
                self.on_note_on(msg.note, msg.velocity)
            else:
                self.on_note_off(msg.note)
        elif msg.type == "note_off":
            self.on_note_off(msg.note)
        elif msg.type == "pitchwheel" and self.on_pitch_bend:
            # Rango ±2 semitonos (CS-80 tenía ±7; configurable en synth)
            semitones = (msg.pitch - 8192) / 8192.0 * 2.0
            self.on_pitch_bend(semitones)
        elif msg.type == "control_change":
            if msg.control == 1 and self.on_mod_wheel:
                self.on_mod_wheel(msg.value / 127.0)
        elif msg.type == "aftertouch" and self.on_aftertouch:
            self.on_aftertouch(msg.value / 127.0)
        elif msg.type == "polytouch" and self.on_aftertouch:
            self.on_aftertouch(msg.value / 127.0)

    def stop(self) -> None:
        self._running = False
        if self._port is not None:
            self._port.close()
            self._port = None
        print("[MIDI] Desconectado.")


def try_start_midi(
    on_note_on: Callable[[int, int], None],
    on_note_off: Callable[[int], None],
    on_pitch_bend: Optional[Callable[[float], None]] = None,
    on_mod_wheel: Optional[Callable[[float], None]] = None,
    on_aftertouch: Optional[Callable[[float], None]] = None,
    port_name: Optional[str] = None,
) -> Optional[MIDIInputHandler]:
    if not MIDI_AVAILABLE:
        print("[MIDI] Librerías no instaladas. Teclado QWERTY disponible en GUI.")
        return None
    try:
        handler = MIDIInputHandler(
            on_note_on, on_note_off, on_pitch_bend, on_mod_wheel, on_aftertouch, port_name
        )
        handler.start()
        return handler
    except Exception as exc:
        print(f"[MIDI] Error al iniciar: {exc}")
        return None
