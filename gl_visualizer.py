"""
Ventana OpenGL fullscreen — visuales aleatorios estilo Winamp.
Detecta monitores y resolución nativa; cubre toda el área del elegido.
Sin menús en la ventana (ESC cierra).
"""

from __future__ import annotations

import math
import os
import random
import sys
import threading
from dataclasses import dataclass
from typing import Callable, List, Optional

import numpy as np

try:
    import pygame
    from OpenGL.GL import (
        GL_BLEND,
        GL_COLOR_BUFFER_BIT,
        GL_DEPTH_BUFFER_BIT,
        GL_LINE_LOOP,
        GL_LINE_SMOOTH,
        GL_LINE_STRIP,
        GL_LINES,
        GL_ONE,
        GL_ONE_MINUS_SRC_ALPHA,
        GL_POINTS,
        GL_PROJECTION,
        GL_QUADS,
        GL_SRC_ALPHA,
        GL_MODELVIEW,
        glBegin,
        glBlendFunc,
        glClear,
        glClearColor,
        glColor4f,
        glEnable,
        glEnd,
        glLineWidth,
        glLoadIdentity,
        glMatrixMode,
        glOrtho,
        glPointSize,
        glVertex2f,
        glViewport,
    )
    from pygame.locals import DOUBLEBUF, FULLSCREEN, KEYDOWN, K_ESCAPE, NOFRAME, OPENGL, QUIT
    OPENGL_OK = True
except ImportError:
    OPENGL_OK = False


@dataclass(frozen=True)
class MonitorInfo:
    index: int
    width: int
    height: int
    x: int = 0
    y: int = 0

    @property
    def label(self) -> str:
        primary = " (principal)" if self.x == 0 and self.y == 0 else ""
        return f"Monitor {self.index + 1}  ·  {self.width}×{self.height}{primary}"


def _ensure_dpi_aware() -> None:
    """Alinea coordenadas WinAPI con píxeles reales (multi-monitor + scaling)."""
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _list_monitors_windows() -> List[MonitorInfo]:
    """Enumera monitores con posición real vía WinAPI."""
    import ctypes
    from ctypes import wintypes

    _ensure_dpi_aware()
    user32 = ctypes.windll.user32

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    monitors: List[MonitorInfo] = []

    MonitorEnumProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )

    def _callback(_hmon, _hdc, lprc, _data):
        r = lprc.contents
        w = int(r.right - r.left)
        h = int(r.bottom - r.top)
        if w > 0 and h > 0:
            monitors.append(
                MonitorInfo(index=len(monitors), width=w, height=h, x=int(r.left), y=int(r.top))
            )
        return True

    cb = MonitorEnumProc(_callback)
    user32.EnumDisplayMonitors(0, 0, cb, 0)
    monitors.sort(key=lambda m: (0 if (m.x == 0 and m.y == 0) else 1, m.x, m.y))
    return [
        MonitorInfo(index=i, width=m.width, height=m.height, x=m.x, y=m.y)
        for i, m in enumerate(monitors)
    ]


def _list_monitors_pygame() -> List[MonitorInfo]:
    """Fallback: tamaños por display con pygame (posiciones estimadas en fila)."""
    if not OPENGL_OK:
        return [MonitorInfo(0, 1920, 1080)]
    if not pygame.display.get_init():
        pygame.display.init()
    try:
        sizes = pygame.display.get_desktop_sizes()
    except Exception:
        info = pygame.display.Info()
        sizes = [(max(info.current_w, 1280), max(info.current_h, 720))]

    out: List[MonitorInfo] = []
    x = 0
    for i, (w, h) in enumerate(sizes):
        out.append(MonitorInfo(index=i, width=int(w), height=int(h), x=x, y=0))
        x += int(w)
    return out or [MonitorInfo(0, 1920, 1080)]


def list_monitors() -> List[MonitorInfo]:
    """Detecta automáticamente todos los monitores disponibles."""
    if sys.platform == "win32":
        try:
            mons = _list_monitors_windows()
            if mons:
                return mons
        except Exception:
            pass
    try:
        return _list_monitors_pygame()
    except Exception:
        return [MonitorInfo(0, 1920, 1080)]


def _force_window_to_monitor(mon: MonitorInfo) -> bool:
    """Mueve la ventana pygame al monitor elegido (SetWindowPos)."""
    if sys.platform != "win32" or not OPENGL_OK:
        return False
    import ctypes
    from ctypes import wintypes

    try:
        info = pygame.display.get_wm_info()
        hwnd = info.get("window")
        if not hwnd:
            return False
    except Exception:
        return False

    user32 = ctypes.windll.user32
    HWND_TOP = 0
    SWP_SHOWWINDOW = 0x0040
    SWP_FRAMECHANGED = 0x0020
    GWL_STYLE = -16
    WS_POPUP = 0x80000000
    WS_VISIBLE = 0x10000000
    WS_CLIPSIBLINGS = 0x04000000
    WS_CLIPCHILDREN = 0x02000000

    try:
        style = WS_POPUP | WS_VISIBLE | WS_CLIPSIBLINGS | WS_CLIPCHILDREN
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            user32.SetWindowLongPtrW(wintypes.HWND(hwnd), GWL_STYLE, style)
        else:
            user32.SetWindowLongW(wintypes.HWND(hwnd), GWL_STYLE, style)
    except Exception:
        pass

    ok = bool(
        user32.SetWindowPos(
            wintypes.HWND(hwnd),
            HWND_TOP,
            int(mon.x),
            int(mon.y),
            int(mon.width),
            int(mon.height),
            SWP_SHOWWINDOW | SWP_FRAMECHANGED,
        )
    )
    try:
        pygame.event.pump()
        ok = bool(
            user32.SetWindowPos(
                wintypes.HWND(hwnd),
                HWND_TOP,
                int(mon.x),
                int(mon.y),
                int(mon.width),
                int(mon.height),
                SWP_SHOWWINDOW,
            )
        ) or ok
    except Exception:
        pass
    return ok


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
    """Fullscreen borderless en el monitor seleccionado (resolución nativa)."""

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

    def __init__(
        self,
        bus: AudioVizBus,
        display_index: int = 0,
        monitor: Optional[MonitorInfo] = None,
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
        if not OPENGL_OK:
            raise RuntimeError(
                "Faltan dependencias OpenGL. Instala: pip install pygame PyOpenGL PyOpenGL-accelerate"
            )
        self.bus = bus
        self.display_index = max(0, int(display_index))
        self._monitor_override = monitor
        self.on_close = on_close
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._monitor = monitor or MonitorInfo(0, 1920, 1080)
        self._w = self._monitor.width
        self._h = self._monitor.height
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

    def _resolve_monitor(self) -> MonitorInfo:
        if self._monitor_override is not None:
            return self._monitor_override
        mons = list_monitors()
        if not mons:
            return MonitorInfo(0, 1920, 1080)
        idx = min(self.display_index, len(mons) - 1)
        return mons[idx]

    def _open_on_monitor(self) -> None:
        """Borderless del tamaño del monitor + anclaje forzado a (x,y)."""
        mon = self._monitor
        self._w, self._h = mon.width, mon.height

        # Nunca FULLSCREEN exclusivo: en Windows siempre cae en el monitor principal.
        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{mon.x},{mon.y}"
        os.environ["SDL_VIDEO_CENTERED"] = "0"

        try:
            try:
                pygame.display.set_mode(
                    (self._w, self._h), DOUBLEBUF | OPENGL | NOFRAME, vsync=1
                )
            except TypeError:
                pygame.display.set_mode((self._w, self._h), DOUBLEBUF | OPENGL | NOFRAME)
        except pygame.error:
            display_idx = self._sdl_display_index(mon)
            try:
                pygame.display.set_mode(
                    (self._w, self._h),
                    DOUBLEBUF | OPENGL | FULLSCREEN,
                    display=display_idx,
                )
            except TypeError:
                pygame.display.set_mode((self._w, self._h), DOUBLEBUF | OPENGL | FULLSCREEN)

        pygame.event.pump()
        _force_window_to_monitor(mon)
        pygame.event.pump()
        _force_window_to_monitor(mon)

        surf = pygame.display.get_surface()
        if surf is not None:
            if surf.get_width() != mon.width or surf.get_height() != mon.height:
                try:
                    pygame.display.set_mode(
                        (mon.width, mon.height), DOUBLEBUF | OPENGL | NOFRAME
                    )
                    pygame.event.pump()
                    _force_window_to_monitor(mon)
                except pygame.error:
                    pass
            surf = pygame.display.get_surface()
            if surf is not None:
                self._w = surf.get_width()
                self._h = surf.get_height()

        pygame.display.set_caption(
            f"CS-80 VIZ  ·  {mon.label}  ·  {self._w}x{self._h}  ·  ESC salir"
        )
        self._setup_gl(self._w, self._h)

    @staticmethod
    def _sdl_display_index(mon: MonitorInfo) -> int:
        try:
            sizes = pygame.display.get_desktop_sizes()
            for i, (w, h) in enumerate(sizes):
                if abs(int(w) - mon.width) <= 8 and abs(int(h) - mon.height) <= 8:
                    return i
        except Exception:
            pass
        return max(0, mon.index)

    def _setup_gl(self, w: int, h: int) -> None:
        w = max(1, int(w))
        h = max(1, int(h))
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(-1.0, 1.0, -1.0, 1.0, -1.0, 1.0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_LINE_SMOOTH)
        glClearColor(0.015, 0.01, 0.04, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

    def _run(self) -> None:
        _ensure_dpi_aware()
        mon = self._resolve_monitor()
        self._monitor = mon
        self._w, self._h = mon.width, mon.height
        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{mon.x},{mon.y}"
        os.environ["SDL_VIDEO_CENTERED"] = "0"

        pygame.init()
        pygame.display.init()
        self._open_on_monitor()
        clock = pygame.time.Clock()
        placed = False

        try:
            while self._running:
                dt = clock.tick(60) / 1000.0
                self._t += dt
                self._effect_timer += dt
                self._hue = (self._hue + dt * 0.05) % 1.0

                if not placed or self._t < 0.35:
                    _force_window_to_monitor(self._monitor)
                    if self._t >= 0.3:
                        placed = True

                for event in pygame.event.get():
                    if event.type == QUIT:
                        self._running = False
                    elif event.type == KEYDOWN and event.key == K_ESCAPE:
                        self._running = False

                if self._effect_timer >= self._effect_duration:
                    self._next_effect()

                scope, spectrum, level = self.bus.snapshot()
                self._draw_frame(scope, spectrum, level, dt)
                pygame.display.flip()
        finally:
            pygame.quit()
            self._running = False
            if self.on_close:
                try:
                    self.on_close()
                except Exception:
                    pass

    def _next_effect(self, force: bool = False) -> None:
        choices = [e for e in self.EFFECTS if e != self.effect]
        self.effect = random.choice(choices)
        self._effect_timer = 0.0
        self._effect_duration = random.uniform(5.0, 16.0)
        if force or random.random() < 0.4:
            self._particles = self._init_particles(180)
            self._stars = self._init_stars(120)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

    def _hsv(self, h: float, s: float, v: float, a: float = 1.0) -> tuple[float, float, float, float]:
        v = min(v, 0.75)
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
        if int(self._t * 10) % 80 == 0:
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

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
        bw = 2.0 / n
        for i, val in enumerate(bins):
            h = min(0.85, (float(val) / peak) * (0.45 + level * 0.5))
            x0 = -1.0 + i * bw + bw * 0.1
            x1 = x0 + bw * 0.8
            r, g, b, a = self._hsv((self._hue + i / n) % 1.0, 0.9, 0.4 + h * 0.35, 0.55)
            glBegin(GL_QUADS)
            glColor4f(r, g, b, a)
            glVertex2f(x0, -0.95)
            glVertex2f(x1, -0.95)
            glColor4f(r, g, b, a * 0.25)
            glVertex2f(x1, -0.95 + h * 1.1)
            glVertex2f(x0, -0.95 + h * 1.1)
            glEnd()
            glBegin(GL_QUADS)
            glColor4f(r, g, b, a * 0.2)
            glVertex2f(x0, 0.95)
            glVertex2f(x1, 0.95)
            glVertex2f(x1, 0.95 - h * 0.55)
            glVertex2f(x0, 0.95 - h * 0.55)
            glEnd()

    def _fx_scope(self, scope: np.ndarray, level: float) -> None:
        glLineWidth(1.5 + level * 2.0)
        n = len(scope)
        glBegin(GL_LINE_STRIP)
        for i, s in enumerate(scope):
            x = -1.0 + 2.0 * i / max(n - 1, 1)
            y = float(s) * (0.4 + level * 0.4)
            r, g, b, a = self._hsv((self._hue + i / n) % 1.0, 0.75, 0.65, 0.55)
            glColor4f(r, g, b, a)
            glVertex2f(x, y)
        glEnd()

    def _fx_tunnel(self, spectrum: np.ndarray, level: float) -> None:
        bass = min(0.4, float(np.mean(spectrum[:8])) if len(spectrum) else 0.0)
        for i in range(14):
            z = ((i / 14) + self._t * (0.25 + bass * 0.4)) % 1.0
            radius = 0.05 + z * 1.35
            bright = (1.0 - z) * (0.25 + level * 0.35 + bass * 0.25)
            r, g, b, a = self._hsv((self._hue + z) % 1.0, 0.9, bright, 0.35)
            glColor4f(r, g, b, a)
            glLineWidth(1.0 + (1.0 - z) * 1.5)
            glBegin(GL_LINE_LOOP)
            for s in range(40):
                ang = 2 * math.pi * s / 40 + self._t * 0.3
                glVertex2f(math.cos(ang) * radius, math.sin(ang) * radius)
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
            radius = 0.3 + 0.2 * math.sin(petals * ang + self._t) + abs(s) * 0.4
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
            radius = 0.12 + i * 0.08 + val * 0.3 + level * 0.1
            r, g, b, a = self._hsv((self._hue + i / max(bands, 1)) % 1.0, 0.9, 0.4 + val * 0.3, 0.35)
            glColor4f(r, g, b, a)
            glLineWidth(1.0 + val * 2.0)
            glBegin(GL_LINE_LOOP)
            for s in range(48):
                ang = 2 * math.pi * s / 48 + self._t * (0.15 + i * 0.03)
                glVertex2f(math.cos(ang) * radius, math.sin(ang) * radius)
            glEnd()


_active_viz: Optional[WinampVisualizer] = None
_active_bus: Optional[AudioVizBus] = None


def get_viz_bus() -> Optional[AudioVizBus]:
    return _active_bus


def launch_visualizer(
    on_close: Optional[Callable[[], None]] = None,
    display_index: int = 0,
    monitor: Optional[MonitorInfo] = None,
) -> tuple[WinampVisualizer, AudioVizBus]:
    global _active_viz, _active_bus
    if not OPENGL_OK:
        raise RuntimeError("pip install pygame PyOpenGL PyOpenGL-accelerate")
    if _active_viz is not None and _active_viz.is_running:
        return _active_viz, _active_bus  # type: ignore

    bus = AudioVizBus()
    viz = WinampVisualizer(
        bus,
        display_index=display_index,
        monitor=monitor,
        on_close=on_close,
    )
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
