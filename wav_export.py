"""
Grabación y exportación de audio a WAV.
"""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Optional

import numpy as np


class AudioRecorder:
    """Acumula muestras del callback de audio para exportar a WAV."""

    def __init__(self, sample_rate: int = 44100) -> None:
        self.sample_rate = sample_rate
        self._chunks: list[np.ndarray] = []
        self.recording = False

    def start(self) -> None:
        self._chunks.clear()
        self.recording = True

    def stop(self) -> None:
        self.recording = False

    def feed(self, samples: np.ndarray) -> None:
        if self.recording:
            if samples.ndim == 2:
                mono = samples.mean(axis=1)
                self._chunks.append(mono.astype(np.float32).copy())
            else:
                self._chunks.append(samples.copy())

    @property
    def duration(self) -> float:
        if not self._chunks:
            return 0.0
        total = sum(len(c) for c in self._chunks)
        return total / self.sample_rate

    def get_buffer(self) -> Optional[np.ndarray]:
        if not self._chunks:
            return None
        return np.concatenate(self._chunks)

    def export_wav(self, path: str | Path) -> Path:
        buffer = self.get_buffer()
        if buffer is None or len(buffer) == 0:
            raise ValueError("No hay audio grabado para exportar.")

        path = Path(path)
        clipped = np.clip(buffer, -1.0, 1.0)
        pcm = (clipped * 32767).astype(np.int16)
        with wave.open(str(path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm.tobytes())

        return path
