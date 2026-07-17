"""
Secuenciador de 16 pasos estilo cinta analógica / Vangelis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Step:
    note: int = 60          # -1 = silencio
    velocity: int = 100
    enabled: bool = True
    accent: bool = False    # velocity boost


@dataclass
class StepPattern:
    name: str = "Pattern A"
    steps: List[Step] = field(default_factory=lambda: [Step() for _ in range(16)])


class StepSequencer:
    NUM_STEPS = 16

    def __init__(self) -> None:
        self.enabled = False
        self.bpm = 100.0
        self.swing = 0.0
        self.pattern = StepPattern()
        self._step_index = 0
        self._phase = 0.0
        self._current_note: Optional[int] = None
        self._gate_open = False

    def set_pattern(self, pattern: StepPattern) -> None:
        self.pattern = pattern
        self._step_index = 0

    def clear(self) -> None:
        self.pattern.steps = [Step(note=-1, enabled=False) for _ in range(self.NUM_STEPS)]

    def toggle_step(self, index: int) -> None:
        if 0 <= index < self.NUM_STEPS:
            self.pattern.steps[index].enabled = not self.pattern.steps[index].enabled

    def set_step_note(self, index: int, note: int) -> None:
        if 0 <= index < self.NUM_STEPS:
            self.pattern.steps[index].note = note
            self.pattern.steps[index].enabled = note >= 0

    def process(self, sample_rate: int, num_samples: int) -> Tuple[Optional[int], int, bool, Optional[int]]:
        """
        Retorna: (nota, velocity, gate_on, nota_off_previa)
        """
        if not self.enabled:
            prev = self._current_note if self._gate_open else None
            self._gate_open = False
            self._current_note = None
            return None, 0, False, prev

        note_off: Optional[int] = None
        samples_per_beat = sample_rate * 60.0 / max(self.bpm, 20.0)
        samples_per_step = samples_per_beat / 4.0  # semicorcheas 16th notes

        for _ in range(num_samples):
            step_duration = samples_per_step
            if self._step_index % 2 == 1 and self.swing > 0:
                step_duration *= 1.0 + self.swing * 0.33

            if self._phase >= step_duration:
                if self._gate_open and self._current_note is not None:
                    note_off = self._current_note
                    self._gate_open = False

                step = self.pattern.steps[self._step_index]
                self._step_index = (self._step_index + 1) % self.NUM_STEPS

                if step.enabled and step.note >= 0:
                    self._current_note = step.note
                    self._gate_open = True
                else:
                    self._current_note = None

                self._phase -= step_duration

            self._phase += 1.0

        if self._gate_open and self._current_note is not None:
            step = self.pattern.steps[(self._step_index - 1) % self.NUM_STEPS]
            vel = min(127, step.velocity + (20 if step.accent else 0))
            return self._current_note, vel, True, note_off

        return None, 0, False, note_off


# Patrones Blade Runner precargados
BLADE_RUNNER_PATTERNS = {
    "BR Main Theme": StepPattern(
        name="BR Main Theme",
        steps=[
            Step(57, 90), Step(-1), Step(60, 85), Step(-1),
            Step(64, 95, accent=True), Step(-1), Step(62, 80), Step(-1),
            Step(60, 90), Step(-1), Step(57, 85), Step(-1),
            Step(55, 95, accent=True), Step(-1), Step(57, 80), Step(60, 100, accent=True),
        ],
    ),
    "Spinner Bass": StepPattern(
        name="Spinner Bass",
        steps=[
            Step(36, 110, accent=True), Step(-1), Step(36, 70), Step(-1),
            Step(43, 100), Step(-1), Step(36, 70), Step(-1),
            Step(36, 110, accent=True), Step(-1), Step(38, 80), Step(-1),
            Step(43, 100), Step(-1), Step(41, 85), Step(-1),
        ],
    ),
    "Rachael Piano": StepPattern(
        name="Rachael Piano",
        steps=[
            Step(72, 75), Step(76, 70), Step(79, 80), Step(76, 65),
            Step(74, 75), Step(71, 70), Step(67, 80), Step(64, 90, accent=True),
            Step(60, 75), Step(64, 70), Step(67, 80), Step(71, 65),
            Step(72, 75), Step(76, 70), Step(79, 85), Step(84, 100, accent=True),
        ],
    ),
    "Officer Deckard": StepPattern(
        name="Officer Deckard",
        steps=[
            Step(48, 95, accent=True), Step(-1), Step(51, 80), Step(55, 85),
            Step(-1), Step(58, 90), Step(55, 75), Step(-1),
            Step(53, 95, accent=True), Step(-1), Step(50, 80), Step(48, 85),
            Step(-1), Step(45, 90, accent=True), Step(48, 80), Step(-1),
        ],
    ),
}
