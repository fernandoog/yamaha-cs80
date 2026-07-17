"""
Perfiles de calidad de audio: Básica → Profesional.
Un solo control elegante cambia sample rate, buffer, antialiasing y acabado.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class SoundQuality(IntEnum):
    BASIC = 0
    STANDARD = 1
    HIGH = 2
    STUDIO = 3
    PRO = 4


@dataclass(frozen=True)
class QualityProfile:
    level: SoundQuality
    label: str
    short: str
    hint: str
    sample_rate: int
    block_size: int
    antialias: bool
    soft_saturate: bool
    dither: bool
    effect_depth: float  # 0..1 intensidad de procesamiento FX
    color: str


QUALITY_PROFILES: dict[SoundQuality, QualityProfile] = {
    SoundQuality.BASIC: QualityProfile(
        level=SoundQuality.BASIC,
        label="Básica",
        short="BAS",
        hint="Ligera · 44.1 kHz · buffer amplio · CPU mínima",
        sample_rate=44100,
        block_size=1024,
        antialias=False,
        soft_saturate=False,
        dither=False,
        effect_depth=0.55,
        color="#5a7a8a",
    ),
    SoundQuality.STANDARD: QualityProfile(
        level=SoundQuality.STANDARD,
        label="Estándar",
        short="STD",
        hint="Equilibrio · 44.1 kHz · latencia media",
        sample_rate=44100,
        block_size=512,
        antialias=False,
        soft_saturate=True,
        dither=False,
        effect_depth=0.75,
        color="#00d4ff",
    ),
    SoundQuality.HIGH: QualityProfile(
        level=SoundQuality.HIGH,
        label="Alta",
        short="HI",
        hint="Más limpia · 48 kHz · antialiasing · buffer corto",
        sample_rate=48000,
        block_size=256,
        antialias=True,
        soft_saturate=True,
        dither=False,
        effect_depth=0.9,
        color="#39ff14",
    ),
    SoundQuality.STUDIO: QualityProfile(
        level=SoundQuality.STUDIO,
        label="Estudio",
        short="STU",
        hint="Producción · 48 kHz · AA + saturación suave + dither",
        sample_rate=48000,
        block_size=128,
        antialias=True,
        soft_saturate=True,
        dither=True,
        effect_depth=1.0,
        color="#ff6b2b",
    ),
    SoundQuality.PRO: QualityProfile(
        level=SoundQuality.PRO,
        label="Profesional",
        short="PRO",
        hint="Máxima fidelidad · 96 kHz · latencia mínima · acabado de estudio",
        sample_rate=96000,
        block_size=128,
        antialias=True,
        soft_saturate=True,
        dither=True,
        effect_depth=1.0,
        color="#ffd700",
    ),
}


def get_profile(level: SoundQuality | int) -> QualityProfile:
    return QUALITY_PROFILES[SoundQuality(int(level))]


def list_qualities() -> list[QualityProfile]:
    return [QUALITY_PROFILES[q] for q in SoundQuality]
