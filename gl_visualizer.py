"""
Ventana OpenGL aparte — visuales aleatorios estilo Winamp / MilkDrop.
Lee el buffer de ondas y espectro del CS80Synth en tiempo real.
"""

from __future__ import annotations

import math
import random
import threading
import time
from typing import Callable, Optional

import numpy as np

try:
    import pygame
    from OpenGL.GL import (
        GL_BLEND,
        GL_CLAMP,
        GL_COLOR_BUFFER_BIT,
        GL_DEPTH_BUFFER_BIT,
        GL_LINEAR,
        GL_LINE_LOOP,
        GL_LINE_SMOOTH,
        GL_LINE_STRIP,
        GL_LINES,
        GL_ONE,
        GL_ONE_MINUS_SRC_ALPHA,
        GL_POINTS,
        GL_PROJECTION,
        GL_QUADS,
        GL_RGBA,
        GL_SRC_ALPHA,
        GL_TEXTURE_2D,
        GL_TEXTURE_MAG_FILTER,
        GL_TEXTURE_MIN_FILTER,
        GL_TEXTURE_WRAP_S,
        GL_TEXTURE_WRAP_T,
        GL_UNSIGNED_BYTE,
        GL_MODELVIEW,
        glBegin,
        glBindTexture,
        glBlendFunc,
        glClear,
        glClearColor,
        glColor4f,
        glDeleteTextures,
        glDisable,
        glEnable,
        glEnd,
        glGenTextures,
        glLineWidth,
        glLoadIdentity,
        glMatrixMode,
        glOrtho,
        glPointSize,
        glTexCoord2f,
        glTexImage2D,
        glTexParameteri,
        glVertex2f,
        glViewport,
    )
    from pygame.locals import (
        DOUBLEBUF,
        FULLSCREEN,
        KEYDOWN,
        K_1,
        K_2,
        K_3,
        K_4,
        K_5,
        K_ESCAPE,
        K_LEFT,
        K_RIGHT,
        K_SPACE,
        K_f,
        K_h,
        K_r,
        NOFRAME,
        OPENGL,
        QUIT,
        RESIZABLE,
        VIDEORESIZE,
    )
    OPENGL_OK = True
except ImportError:
    OPENGL_OK = False


class AudioVizBus:
    """Puente thread-safe entre el synth y la ventana OpenGL."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.scope = np.zeros(512, dtype=np.float32)
        self.spectrum = np.zeros(128, dtype=np.float32)
        self.level = 0.0
        self.alive = True

    def push(self, scope: np.ndarray, spectrum: np.ndarray) -> None:
        with self._lock:
            n = min(len(scope), len(self.scope))
            self.scope[:n] = scope[:n]
            m = min(len(spectrum), len(self.spectrum))
            self.spectrum[:m] = spectrum[:m]
            self.level = float(np.sqrt(np.mean(scope[:n] ** 2))) if n else 0.0

    def snapshot(self) -> tuple[np.ndarray, np.ndarray, float]:
        with self._lock:
            return self.scope.copy(), self.spectrum.copy(), self.level


class WinampVisualizer:
    """Efectos aleatorios estilo Winamp en ventana OpenGL independiente."""

    EFFECTS = (
        "spectrum_bars",
        "oscilloscope",
        "tunnel",
        "plasma",
        "particles",
        "starfield",
        "flower",
        "grid_pulse",
        "rings",
    )

    # Resoluciones de ventana (fácil: teclas 1-5). FULL = monitor nativo.
    RES_PRESETS = (
        ("800×600", 800, 600),
        ("1280×720", 1280, 720),
        ("1600×900", 1600, 900),
        ("1920×1080", 1920, 1080),
        ("Pantalla nativa", 0, 0),  # 0,0 = desktop size
    )

    def __init__(
        self,
        bus: AudioVizBus,
        width: int = 1280,
        height: int = 720,
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
        if not OPENGL_OK:
            raise RuntimeError(
                "Faltan dependencias OpenGL. Instala: pip install pygame PyOpenGL PyOpenGL-accelerate"
            )
        self.bus = bus
        self.width = width
        self.height = height
        self.on_close = on_close
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._fullscreen = False
        self._desktop_w = width
        self._desktop_h = height
        self._win_w = width
        self._win_h = height
        self._res_index = 1  # 1280×720 por defecto
        self._show_hud = True
        self._hud_tex = None
        self._hud_w = 1
        self._hud_h = 1
        self._hud_dirty = True
        self._hint_timer = 4.0
        self.effect = random.choice(self.EFFECTS)
        self._effect_timer = 0.0
        self._effect_duration = random.uniform(6.0, 14.0)
        self._t = 0.0
        self._particles = self._init_particles(180)
        self._stars = self._init_stars(120)
        self._hue = random.random()

    def _init_particles(self, n: int) -> list[dict]:
        return [
            {
                "x": random.uniform(-1, 1),
                "y": random.uniform(-1, 1),
                "vx": random.uniform(-0.3, 0.3),
                "vy": random.uniform(-0.3, 0.3),
                "life": random.random(),
            }
            for _ in range(n)
        ]

    def _init_stars(self, n: int) -> list[dict]:
        return [
            {
                "x": random.uniform(-1, 1),
                "y": random.uniform(-1, 1),
                "z": random.uniform(0.1, 1.0),
            }
            for _ in range(n)
        ]

    def _read_desktop_size(self) -> tuple[int, int]:
        try:
            sizes = pygame.display.get_desktop_sizes()
            if sizes:
                return int(sizes[0][0]), int(sizes[0][1])
        except Exception:
            pass
        info = pygame.display.Info()
        return max(info.current_w, 1280), max(info.current_h, 720)

    def _preset_size(self, index: int) -> tuple[int, int, str]:
        name, w, h = self.RES_PRESETS[index]
        if w <= 0 or h <= 0:
            return self._desktop_w, self._desktop_h, f"{name} ({self._desktop_w}×{self._desktop_h})"
        # No superar el escritorio en modo ventana
        w = min(w, self._desktop_w)
        h = min(h, self._desktop_h)
        return w, h, f"{name}"

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.bus.alive = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="WinampGL")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self.bus.alive = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    @property
    def is_running(self) -> bool:
        return self._running

    def _run(self) -> None:
        pygame.init()
        pygame.display.init()
        pygame.font.init()
        self._desktop_w, self._desktop_h = self._read_desktop_size()
        self.width, self.height, _ = self._preset_size(self._res_index)

        self._apply_display(fullscreen=False)
        self._update_caption()
        clock = pygame.time.Clock()

        try:
            while self._running:
                dt = clock.tick(60) / 1000.0
                self._t += dt
                self._effect_timer += dt
                self._hue = (self._hue + dt * 0.05) % 1.0
                if self._hint_timer > 0:
                    self._hint_timer -= dt

                for event in pygame.event.get():
                    if event.type == QUIT:
                        self._running = False
                    elif event.type == VIDEORESIZE and not self._fullscreen:
                        self.width = max(640, event.w)
                        self.height = max(360, event.h)
                        self._apply_display(fullscreen=False)
                        self._hud_dirty = True
                        self._update_caption()
                    elif event.type == KEYDOWN:
                        self._handle_key(event.key)

                if self._effect_timer >= self._effect_duration:
                    self._next_effect()

                scope, spectrum, level = self.bus.snapshot()
                self._draw_frame(scope, spectrum, level, dt)
                if self._show_hud:
                    self._draw_hud()
                pygame.display.flip()
        finally:
            self._destroy_hud_texture()
            pygame.quit()
            self._running = False
            if self.on_close:
                try:
                    self.on_close()
                except Exception:
                    pass

    def _handle_key(self, key: int) -> None:
        if key == K_ESCAPE:
            if self._fullscreen:
                self._set_fullscreen(False)
            else:
                self._running = False
        elif key == K_SPACE:
            self._next_effect(force=True)
        elif key == K_f:
            self._set_fullscreen(not self._fullscreen)
        elif key == K_h:
            self._show_hud = not self._show_hud
            self._hint_timer = 2.0
        elif key == K_r or key == K_RIGHT:
            self._cycle_resolution(1)
        elif key == K_LEFT:
            self._cycle_resolution(-1)
        elif key == K_1:
            self._set_resolution(0)
        elif key == K_2:
            self._set_resolution(1)
        elif key == K_3:
            self._set_resolution(2)
        elif key == K_4:
            self._set_resolution(3)
        elif key == K_5:
            self._set_resolution(4)

    def _cycle_resolution(self, delta: int) -> None:
        self._set_resolution((self._res_index + delta) % len(self.RES_PRESETS))

    def _set_resolution(self, index: int) -> None:
        self._res_index = max(0, min(len(self.RES_PRESETS) - 1, index))
        w, h, label = self._preset_size(self._res_index)
        self.width, self.height = w, h
        self._hint_timer = 3.0
        self._hud_dirty = True
        # En fullscreen: siempre cubrir todo el monitor (nativo)
        if self._fullscreen:
            self._apply_display(fullscreen=True)
        else:
            self._apply_display(fullscreen=False)
        self._update_caption()
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

    def _update_caption(self) -> None:
        _, _, label = self._preset_size(self._res_index)
        mode = "FULLSCREEN" if self._fullscreen else "VENTANA"
        pygame.display.set_caption(
            f"CS-80 VIZ  |  {self._win_w}×{self._win_h} ({label})  |  {mode}  |  "
            f"1-5 resolución  ←→  |  F pantalla completa  |  H ayuda  |  SPACE efecto"
        )

    def _apply_display(self, fullscreen: bool) -> None:
        """Crea la superficie OpenGL. Fullscreen = 100% del área del monitor."""
        import os

        self._desktop_w, self._desktop_h = self._read_desktop_size()

        if fullscreen:
            w, h = self._desktop_w, self._desktop_h
            os.environ["SDL_VIDEO_WINDOW_POS"] = "0,0"
            # FULLSCREEN exclusivo a resolución nativa — cubre toda el área
            created = False
            for flags in (
                DOUBLEBUF | OPENGL | FULLSCREEN,
                DOUBLEBUF | OPENGL | NOFRAME,
            ):
                try:
                    try:
                        pygame.display.set_mode((w, h), flags, vsync=1)
                    except TypeError:
                        pygame.display.set_mode((w, h), flags)
                    surf = pygame.display.get_surface()
                    if surf is not None and surf.get_width() >= int(w * 0.98) and surf.get_height() >= int(h * 0.98):
                        created = True
                        break
                except pygame.error:
                    continue
            if not created:
                try:
                    pygame.display.set_mode((0, 0), DOUBLEBUF | OPENGL | FULLSCREEN)
                except Exception:
                    pygame.display.set_mode((w, h), DOUBLEBUF | OPENGL | FULLSCREEN)
        else:
            os.environ["SDL_VIDEO_WINDOW_POS"] = "centered"
            w, h = self.width, self.height
            try:
                pygame.display.set_mode((w, h), DOUBLEBUF | OPENGL | RESIZABLE, vsync=1)
            except TypeError:
                pygame.display.set_mode((w, h), DOUBLEBUF | OPENGL | RESIZABLE)

        surf = pygame.display.get_surface()
        if surf is not None:
            self._win_w = surf.get_width()
            self._win_h = surf.get_height()
        else:
            self._win_w, self._win_h = w, h
        self._setup_gl(self._win_w, self._win_h)
        self._hud_dirty = True

    def _set_fullscreen(self, enabled: bool) -> None:
        self._fullscreen = enabled
        self._apply_display(fullscreen=enabled)
        self._update_caption()
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

    def _toggle_fullscreen(self) -> None:
        self._set_fullscreen(not self._fullscreen)

    def _setup_gl(self, w: int, h: int) -> None:
        w = max(1, int(w))
        h = max(1, int(h))
        # Viewport a toda la superficie (sin letterbox)
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(-1, 1, -1, 1, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_LINE_SMOOTH)
        glClearColor(0.015, 0.01, 0.04, 1.0)

    def _destroy_hud_texture(self) -> None:
        if self._hud_tex is not None:
            try:
                glDeleteTextures([self._hud_tex])
            except Exception:
                pass
            self._hud_tex = None

    def _rebuild_hud_texture(self) -> None:
        _, _, label = self._preset_size(self._res_index)
        mode = "FULLSCREEN · monitor completo" if self._fullscreen else "ventana"
        lines = [
            f"  RESOLUCIÓN:  {self._win_w}×{self._win_h}   ({label})   ·   {mode}",
            "  [1] 800×600   [2] 720p   [3] 1600×900   [4] 1080p   [5] Nativa",
            "  ← → cambiar   F pantalla completa   SPACE efecto   H ocultar ayuda   ESC salir",
        ]
        font = pygame.font.SysFont("consolas", 18, bold=True)
        small = pygame.font.SysFont("consolas", 15)
        rendered = [
            font.render(lines[0], True, (0, 220, 255)),
            small.render(lines[1], True, (200, 230, 240)),
            small.render(lines[2], True, (140, 170, 180)),
        ]
        pad_x, pad_y = 16, 10
        gap = 4
        tw = max(s.get_width() for s in rendered) + pad_x * 2
        th = sum(s.get_height() for s in rendered) + gap * (len(rendered) - 1) + pad_y * 2
        # potencias de 2 para texturas antiguas (seguro)
        tex_w = 1
        tex_h = 1
        while tex_w < tw:
            tex_w *= 2
        while tex_h < th:
            tex_h *= 2

        surf = pygame.Surface((tex_w, tex_h), pygame.SRCALPHA)
        surf.fill((8, 12, 20, 200))
        y = pad_y
        for s in rendered:
            surf.blit(s, (pad_x, y))
            y += s.get_height() + gap

        # Barra de presets
        bar_y = th - 8
        n = len(self.RES_PRESETS)
        for i in range(n):
            x0 = int(pad_x + i * (tw - pad_x * 2) / n)
            x1 = int(pad_x + (i + 1) * (tw - pad_x * 2) / n) - 4
            color = (255, 107, 43, 255) if i == self._res_index else (40, 70, 90, 255)
            pygame.draw.rect(surf, color, (x0, bar_y, max(4, x1 - x0), 4))

        data = pygame.image.tostring(surf, "RGBA", True)
        self._destroy_hud_texture()
        self._hud_tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self._hud_tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, tex_w, tex_h, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
        self._hud_w = tw / tex_w
        self._hud_h = th / tex_h
        self._hud_tex_aspect = tw / max(th, 1)
        self._hud_pixel_w = tw
        self._hud_pixel_h = th
        self._hud_dirty = False

    def _draw_hud(self) -> None:
        if self._hud_dirty or self._hud_tex is None:
            try:
                self._rebuild_hud_texture()
            except Exception:
                return
        if self._hud_tex is None:
            return

        # Tamaño HUD en NDC según píxeles de pantalla
        margin = 0.04
        hud_h = min(0.22, (self._hud_pixel_h / max(self._win_h, 1)) * 2.0)
        hud_w = min(1.9, hud_h * self._hud_tex_aspect * (self._win_h / max(self._win_w, 1)) * 2)
        # Anclar abajo-centro
        x0 = -hud_w / 2
        x1 = hud_w / 2
        y0 = -1.0 + margin
        y1 = y0 + hud_h
        u, v = self._hud_w, self._hud_h

        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self._hud_tex)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(1, 1, 1, 0.92 if self._hint_timer > 0 else 0.55)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0)
        glVertex2f(x0, y0)
        glTexCoord2f(u, 0)
        glVertex2f(x1, y0)
        glTexCoord2f(u, v)
        glVertex2f(x1, y1)
        glTexCoord2f(0, v)
        glVertex2f(x0, y1)
        glEnd()
        glDisable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, 0)

    def _next_effect(self, force: bool = False) -> None:
        choices = [e for e in self.EFFECTS if e != self.effect]
        self.effect = random.choice(choices)
        self._effect_timer = 0.0
        self._effect_duration = random.uniform(5.0, 16.0)
        if force or random.random() < 0.4:
            self._particles = self._init_particles(180)
            self._stars = self._init_stars(120)
        # Limpiar al cambiar efecto para evitar acumulación
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

    def _hsv(self, h: float, s: float, v: float, a: float = 1.0) -> tuple[float, float, float, float]:
        v = min(v, 0.75)  # tope de brillo — evita lavado a blanco
        a = min(a, 0.7)
        i = int(h * 6.0) % 6
        f = h * 6.0 - int(h * 6.0)
        p = v * (1.0 - s)
        q = v * (1.0 - f * s)
        t = v * (1.0 - (1.0 - f) * s)
        if i == 0:
            r, g, b = v, t, p
        elif i == 1:
            r, g, b = q, v, p
        elif i == 2:
            r, g, b = p, v, t
        elif i == 3:
            r, g, b = p, q, v
        elif i == 4:
            r, g, b = t, p, v
        else:
            r, g, b = v, p, q
        return r, g, b, a

    def _norm_level(self, level: float) -> float:
        return min(0.45, max(0.0, level * 1.8))

    def _fade_frame(self) -> None:
        """Oscurece el frame anterior (trails estables, sin sumar a blanco)."""
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glBegin(GL_QUADS)
        glColor4f(0.015, 0.01, 0.04, 0.28)
        glVertex2f(-1, -1)
        glVertex2f(1, -1)
        glVertex2f(1, 1)
        glVertex2f(-1, 1)
        glEnd()

    def _draw_frame(self, scope: np.ndarray, spectrum: np.ndarray, level: float, dt: float) -> None:
        level = self._norm_level(level)
        self._fade_frame()

        # Limpieza periódica más frecuente
        if int(self._t * 10) % 80 == 0:
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # Efectos con blending aditivo suave (brillo controlado)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)

        name = self.effect
        if name == "spectrum_bars":
            self._fx_spectrum(spectrum, level)
        elif name == "oscilloscope":
            self._fx_scope(scope, level)
        elif name == "tunnel":
            self._fx_tunnel(spectrum, level)
        elif name == "plasma":
            self._fx_plasma(level)
        elif name == "particles":
            self._fx_particles(scope, level, dt)
        elif name == "starfield":
            self._fx_starfield(level, dt)
        elif name == "flower":
            self._fx_flower(scope, level)
        elif name == "grid_pulse":
            self._fx_grid(spectrum, level)
        else:
            self._fx_rings(spectrum, level)

        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    def _fx_spectrum(self, spectrum: np.ndarray, level: float) -> None:
        n = max(8, len(spectrum) // 2)
        bins = spectrum[:n]
        peak = float(np.max(bins)) + 1e-6
        w = 2.0 / n
        for i, val in enumerate(bins):
            h = min(0.85, (float(val) / peak) * (0.45 + level * 0.5))
            x0 = -1.0 + i * w + w * 0.1
            x1 = x0 + w * 0.8
            r, g, b, a = self._hsv((self._hue + i / n) % 1.0, 0.9, 0.4 + h * 0.35, 0.55)
            glBegin(GL_QUADS)
            glColor4f(r, g, b, a)
            glVertex2f(x0, -0.85)
            glVertex2f(x1, -0.85)
            glColor4f(r, g, b, a * 0.25)
            glVertex2f(x1, -0.85 + h)
            glVertex2f(x0, -0.85 + h)
            glEnd()
            glBegin(GL_QUADS)
            glColor4f(r, g, b, a * 0.2)
            glVertex2f(x0, 0.85)
            glVertex2f(x1, 0.85)
            glVertex2f(x1, 0.85 - h * 0.5)
            glVertex2f(x0, 0.85 - h * 0.5)
            glEnd()

    def _fx_scope(self, scope: np.ndarray, level: float) -> None:
        glLineWidth(1.5 + level * 2.0)
        glBegin(GL_LINE_STRIP)
        n = len(scope)
        for i, s in enumerate(scope):
            x = -1.0 + 2.0 * i / max(n - 1, 1)
            y = float(s) * (0.35 + level * 0.4)
            r, g, b, a = self._hsv((self._hue + i / n) % 1.0, 0.75, 0.65, 0.55)
            glColor4f(r, g, b, a)
            glVertex2f(x, y)
        glEnd()
        glLineWidth(1.0)
        glBegin(GL_LINE_STRIP)
        for i, s in enumerate(scope):
            x = -1.0 + 2.0 * i / max(n - 1, 1)
            y = float(s) * (0.2 + level * 0.25) + 0.05 * math.sin(self._t + i * 0.05)
            r, g, b, a = self._hsv((self._hue + 0.3) % 1.0, 0.6, 0.45, 0.3)
            glColor4f(r, g, b, a)
            glVertex2f(x, y)
        glEnd()

    def _fx_tunnel(self, spectrum: np.ndarray, level: float) -> None:
        bass = min(0.4, float(np.mean(spectrum[:8])) if len(spectrum) else 0.0)
        rings = 14
        for i in range(rings):
            z = ((i / rings) + self._t * (0.25 + bass * 0.4)) % 1.0
            radius = 0.05 + z * 1.1
            bright = (1.0 - z) * (0.25 + level * 0.35 + bass * 0.25)
            r, g, b, a = self._hsv((self._hue + z) % 1.0, 0.9, bright, 0.35)
            glColor4f(r, g, b, a)
            glLineWidth(1.0 + (1.0 - z) * 1.5)
            glBegin(GL_LINE_LOOP)
            segs = 40
            for s in range(segs):
                ang = 2 * math.pi * s / segs + self._t * 0.3
                glVertex2f(math.cos(ang) * radius, math.sin(ang) * radius * 0.75)
            glEnd()

    def _fx_plasma(self, level: float) -> None:
        steps = 28
        for y in range(steps):
            for x in range(steps):
                u = x / (steps - 1) * 2 - 1
                v = y / (steps - 1) * 2 - 1
                val = (
                    math.sin(u * 4 + self._t * 1.1)
                    + math.sin(v * 5 - self._t * 0.8)
                    + math.sin((u + v) * 3 + self._t * 0.5)
                    + level
                ) / 5.0
                r, g, b, a = self._hsv((val * 0.4 + self._hue) % 1.0, 0.85, 0.25 + abs(val) * 0.3, 0.18)
                sz = 2.0 / steps
                glBegin(GL_QUADS)
                glColor4f(r, g, b, a)
                glVertex2f(u, v)
                glVertex2f(u + sz, v)
                glVertex2f(u + sz, v + sz)
                glVertex2f(u, v + sz)
                glEnd()

    def _fx_particles(self, scope: np.ndarray, level: float, dt: float) -> None:
        mid = float(scope[len(scope) // 2]) if len(scope) else 0.0
        glPointSize(1.5 + level * 3.0)
        glBegin(GL_POINTS)
        for p in self._particles:
            p["x"] += p["vx"] * dt * (0.8 + level * 1.5)
            p["y"] += p["vy"] * dt * (0.8 + level * 1.5)
            p["life"] -= dt * 0.2
            if abs(p["x"]) > 1.2 or abs(p["y"]) > 1.2 or p["life"] <= 0:
                p["x"] = mid * 0.15
                p["y"] = random.uniform(-0.08, 0.08)
                p["vx"] = random.uniform(-0.6, 0.6)
                p["vy"] = random.uniform(-0.6, 0.6)
                p["life"] = 1.0
            r, g, b, a = self._hsv((self._hue + p["life"] * 0.2) % 1.0, 0.9, 0.55, p["life"] * 0.45)
            glColor4f(r, g, b, a)
            glVertex2f(p["x"], p["y"])
        glEnd()

    def _fx_starfield(self, level: float, dt: float) -> None:
        speed = 0.3 + level * 1.2
        for s in self._stars:
            s["z"] -= dt * speed
            if s["z"] <= 0.05:
                s["x"] = random.uniform(-1, 1)
                s["y"] = random.uniform(-1, 1)
                s["z"] = 1.0
            k = 1.0 / s["z"]
            x = s["x"] * k
            y = s["y"] * k
            if abs(x) > 1.2 or abs(y) > 1.2:
                s["z"] = 0.05
                continue
            bright = (1.0 - s["z"]) * (0.3 + level * 0.4)
            r, g, b, a = self._hsv(self._hue, 0.45, bright, 0.5)
            glPointSize(1.0 + (1.0 - s["z"]) * 2.5)
            glBegin(GL_POINTS)
            glColor4f(r, g, b, a)
            glVertex2f(x, y)
            glEnd()

    def _fx_flower(self, scope: np.ndarray, level: float) -> None:
        petals = 5 + int(level * 5)
        glLineWidth(1.2)
        glBegin(GL_LINE_LOOP)
        n = 180
        for i in range(n):
            ang = 2 * math.pi * i / n
            s = float(scope[i % len(scope)]) if len(scope) else 0.0
            radius = 0.22 + 0.15 * math.sin(petals * ang + self._t) + abs(s) * 0.35
            r, g, b, a = self._hsv((self._hue + i / n) % 1.0, 0.85, 0.55, 0.5)
            glColor4f(r, g, b, a)
            glVertex2f(math.cos(ang) * radius, math.sin(ang) * radius)
        glEnd()

    def _fx_grid(self, spectrum: np.ndarray, level: float) -> None:
        bass = min(0.35, float(np.mean(spectrum[:6])) if len(spectrum) else 0.0)
        pulse = 0.05 + bass * 0.2 + level * 0.12
        glLineWidth(1.0)
        for i in range(-8, 9):
            o = i / 8.0
            r, g, b, a = self._hsv((self._hue + abs(o)) % 1.0, 0.7, 0.3 + pulse, 0.28)
            glColor4f(r, g, b, a)
            glBegin(GL_LINES)
            glVertex2f(o, -1)
            glVertex2f(o + math.sin(self._t + o) * pulse * 0.2, 1)
            glVertex2f(-1, o)
            glVertex2f(1, o + math.cos(self._t + o) * pulse * 0.2)
            glEnd()

    def _fx_rings(self, spectrum: np.ndarray, level: float) -> None:
        bands = min(10, len(spectrum))
        for i in range(bands):
            val = min(0.5, float(spectrum[i]) if len(spectrum) else 0.0)
            radius = 0.1 + i * 0.07 + val * 0.25 + level * 0.08
            r, g, b, a = self._hsv((self._hue + i / max(bands, 1)) % 1.0, 0.9, 0.4 + val * 0.3, 0.35)
            glColor4f(r, g, b, a)
            glLineWidth(1.0 + val * 2.0)
            glBegin(GL_LINE_LOOP)
            for s in range(48):
                ang = 2 * math.pi * s / 48 + self._t * (0.15 + i * 0.03)
                glVertex2f(math.cos(ang) * radius, math.sin(ang) * radius * 0.85)
            glEnd()

_active_viz: Optional[WinampVisualizer] = None
_active_bus: Optional[AudioVizBus] = None


def get_viz_bus() -> Optional[AudioVizBus]:
    return _active_bus


def launch_visualizer(on_close: Optional[Callable[[], None]] = None) -> tuple[WinampVisualizer, AudioVizBus]:
    global _active_viz, _active_bus
    if not OPENGL_OK:
        raise RuntimeError("pip install pygame PyOpenGL PyOpenGL-accelerate")
    if _active_viz is not None and _active_viz.is_running:
        return _active_viz, _active_bus  # type: ignore

    bus = AudioVizBus()
    viz = WinampVisualizer(bus, on_close=on_close)
    viz.start()
    _active_viz = viz
    _active_bus = bus
    return viz, bus


def stop_visualizer() -> None:
    global _active_viz, _active_bus
    if _active_viz is not None:
        _active_viz.stop()
    _active_viz = None
    _active_bus = None
