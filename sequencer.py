"""
Arpegiador / secuenciador simple inspirado en líneas de Vangelis.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional


class ArpMode(str, Enum):
    UP = "up"
    DOWN = "down"
    UP_DOWN = "up_down"
    RANDOM = "random"


class Arpeggiator:
    """Arpegiador que cicla notas mantenidas."""

    def __init__(self) -> None:
        self.enabled = False
        self.rate_hz = 4.0
        self.mode = ArpMode.UP
        self.octaves = 1
        self.gate = 0.8
        self._held_notes: List[int] = []
        self._sorted: List[int] = []
        self._index = 0
        self._direction = 1
        self._phase = 0.0
        self._current_note: Optional[int] = None
        self._gate_open = False
        self._rng_state = 42

    def set_held_notes(self, notes: List[int]) -> None:
        self._held_notes = sorted(set(notes))
        self._rebuild_sequence()

    def _rebuild_sequence(self) -> None:
        if not self._held_notes:
            self._sorted = []
            return
        seq: List[int] = []
        for oct_ in range(self.octaves):
            for n in self._held_notes:
                seq.append(n + oct_ * 12)
        self._sorted = seq
        self._index = 0

    def _next_random(self) -> int:
        self._rng_state = (self._rng_state * 1103515245 + 12345) & 0x7FFFFFFF
        if not self._sorted:
            return 60
        return self._sorted[self._rng_state % len(self._sorted)]

    def _next_note(self) -> Optional[int]:
        if not self._sorted:
            return None
        if self.mode == ArpMode.UP:
            note = self._sorted[self._index % len(self._sorted)]
            self._index += 1
        elif self.mode == ArpMode.DOWN:
            note = self._sorted[-(self._index % len(self._sorted)) - 1]
            self._index += 1
        elif self.mode == ArpMode.UP_DOWN:
            note = self._sorted[self._index]
            self._index += self._direction
            if self._index >= len(self._sorted) - 1:
                self._direction = -1
            elif self._index <= 0:
                self._direction = 1
        else:
            note = self._next_random()
        return note

    def process(self, sample_rate: int, num_samples: int) -> tuple[Optional[int], bool, Optional[int]]:
        """
        Avanza el arpegiador.
        Retorna: (nota_actual, gate_on, nota_anterior_para_note_off)
        """
        if not self.enabled or not self._sorted:
            prev = self._current_note
            self._current_note = None
            self._gate_open = False
            return None, False, prev

        note_off: Optional[int] = None
        samples_per_step = sample_rate / max(self.rate_hz, 0.1)
        gate_samples = samples_per_step * self.gate

        for _ in range(num_samples):
            if self._phase >= samples_per_step:
                if self._gate_open and self._current_note is not None:
                    note_off = self._current_note
                self._current_note = self._next_note()
                self._gate_open = True
                self._phase -= samples_per_step
            elif self._phase >= gate_samples and self._gate_open:
                if self._current_note is not None:
                    note_off = self._current_note
                self._gate_open = False
            self._phase += 1.0

        if self._gate_open:
            return self._current_note, True, note_off
        return None, False, note_off
