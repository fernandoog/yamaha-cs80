"""
PASO 2: Motor de audio básico
-------------------------------
Generación de ondas, salida en tiempo real vía sounddevice.
Compatible Linux / Windows.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

import numpy as np

try:
    import sounddevice as sd
except ImportError as exc:
    raise ImportError(
        "sounddevice no está instalado. Ejecuta: pip install sounddevice numpy"
    ) from exc


SAMPLE_RATE = 44100
BLOCK_SIZE = 512
DEFAULT_CHANNELS = 2


def midi_to_freq(note: int) -> float:
    """Convierte número MIDI (0-127) a frecuencia en Hz."""
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


class WaveGenerator:
    """Generadores de onda básicos para el sintetizador."""

    @staticmethod
    def sine(phase: np.ndarray) -> np.ndarray:
        return np.sin(2.0 * np.pi * phase)

    @staticmethod
    def saw(phase: np.ndarray) -> np.ndarray:
        return 2.0 * (phase - np.floor(phase + 0.5))

    @staticmethod
    def square(phase: np.ndarray) -> np.ndarray:
        return np.sign(WaveGenerator.saw(phase))

    @staticmethod
    def triangle(phase: np.ndarray) -> np.ndarray:
        return 2.0 * np.abs(2.0 * (phase - np.floor(phase + 0.5))) - 1.0

    @staticmethod
    def noise(num_samples: int, rng: np.random.Generator) -> np.ndarray:
        return rng.uniform(-1.0, 1.0, num_samples)

    @staticmethod
    def _polyblep(phase: np.ndarray, phase_inc: np.ndarray) -> np.ndarray:
        """Corrección PolyBLEP para suavizar aliasing en bordes de onda."""
        t = phase
        dt = np.maximum(phase_inc, 1e-9)
        out = np.zeros_like(t)
        mask1 = t < dt
        t1 = t[mask1] / dt[mask1]
        out[mask1] = t1 + t1 - t1 * t1 - 1.0
        mask2 = t > 1.0 - dt
        t2 = (t[mask2] - 1.0) / dt[mask2]
        out[mask2] = t2 * t2 + t2 + t2 + 1.0
        return out

    @staticmethod
    def saw_aa(phase: np.ndarray, phase_inc) -> np.ndarray:
        """Diente de sierra con antialiasing PolyBLEP."""
        if np.isscalar(phase_inc):
            inc = np.full_like(phase, float(phase_inc))
        else:
            inc = np.asarray(phase_inc, dtype=np.float64)
        return WaveGenerator.saw(phase) - WaveGenerator._polyblep(phase, inc)

    @staticmethod
    def square_aa(phase: np.ndarray, phase_inc, duty: float = 0.5) -> np.ndarray:
        """Cuadrada con antialiasing PolyBLEP."""
        if np.isscalar(phase_inc):
            inc = np.full_like(phase, float(phase_inc))
        else:
            inc = np.asarray(phase_inc, dtype=np.float64)
        t2 = (phase + duty) % 1.0
        return (
            np.where(phase < duty, 1.0, -1.0)
            + WaveGenerator._polyblep(phase, inc)
            - WaveGenerator._polyblep(t2, inc)
        )


class AudioEngine:
    """
    Motor de audio en tiempo real.

    Inicializa el dispositivo de salida y reproduce buffers generados
    por un callback de síntesis.
    """

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        block_size: int = BLOCK_SIZE,
        channels: int = DEFAULT_CHANNELS,
    ) -> None:
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.channels = channels
        self._callback_fn: Optional[Callable[[int], np.ndarray]] = None
        self._stream: Optional[sd.OutputStream] = None
        self._lock = threading.Lock()
        self._running = False

    @staticmethod
    def list_devices() -> None:
        """Lista dispositivos de audio disponibles (útil para depuración)."""
        print(sd.query_devices())

    def configure(self, sample_rate: int, block_size: int) -> bool:
        """
        Cambia sample rate / buffer. Si el audio está activo, reinicia el stream.
        Devuelve True si el stream quedó activo de nuevo.
        """
        was_running = self._running
        callback = self._callback_fn
        if was_running:
            self.stop()
        self.sample_rate = int(sample_rate)
        self.block_size = int(block_size)
        if was_running and callback is not None:
            try:
                self.start(callback)
            except Exception:
                # Reintento con valores seguros
                self.sample_rate = SAMPLE_RATE
                self.block_size = BLOCK_SIZE
                self.start(callback)
                raise
            return True
        return False

    def start(self, callback_fn: Callable[[int], np.ndarray]) -> None:
        """
        Inicia la reproducción en tiempo real.

        callback_fn: función que recibe block_size y devuelve un array float32.
        """
        with self._lock:
            if self._running:
                return
            self._callback_fn = callback_fn
            self._stream = sd.OutputStream(
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                channels=self.channels,
                dtype="float32",
                callback=self._audio_callback,
            )
            self._stream.start()
            self._running = True

    def stop(self) -> None:
        """Detiene y libera el dispositivo de audio."""
        with self._lock:
            if not self._running:
                return
            self._running = False
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            self._callback_fn = None

    @property
    def is_running(self) -> bool:
        return self._running

    def _audio_callback(
        self,
        outdata: np.ndarray,
        frames: int,
        _time_info,
        _status,
    ) -> None:
        if self._callback_fn is None:
            outdata.fill(0)
            return

        samples = self._callback_fn(frames)
        if samples.ndim == 1:
            if self.channels == 1:
                outdata[:, 0] = samples[:frames]
            else:
                mono = samples[:frames]
                outdata[:, 0] = mono
                outdata[:, 1] = mono
        else:
            outdata[:] = samples[:frames]

    def play_test_tone(
        self,
        frequency: float = 440.0,
        duration: float = 2.0,
    ) -> None:
        """
        Ejemplo mínimo: tono continuo que se detiene correctamente.
        Uso: python -m audio_engine
        """
        phase = 0.0
        phase_inc = frequency / self.sample_rate

        def tone_callback(frames: int) -> np.ndarray:
            nonlocal phase
            t = np.arange(frames, dtype=np.float64)
            phases = (phase + t * phase_inc) % 1.0
            phase = (phase + frames * phase_inc) % 1.0
            return (0.3 * WaveGenerator.sine(phases)).astype(np.float32)

        print(f"[AudioEngine] Reproduciendo tono {frequency:.1f} Hz durante {duration}s...")
        self.start(tone_callback)
        try:
            sd.sleep(int(duration * 1000))
        finally:
            self.stop()
            print("[AudioEngine] Tono detenido. Dispositivo liberado.")


if __name__ == "__main__":
    engine = AudioEngine()
    print("[AudioEngine] Dispositivos de audio:")
    AudioEngine.list_devices()
    engine.play_test_tone(440.0, 2.0)
