"""
Interfaz Blade Runner ampliada: pestañas, osciloscopio, piano virtual,
efectos, capa II, arpegiador y grabación WAV.
"""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from audio_engine import AudioEngine, BLOCK_SIZE, SAMPLE_RATE
from effects import EffectParams
from presets import get_preset, list_presets, load_preset
from gl_visualizer import OPENGL_OK, get_viz_bus, launch_visualizer, list_monitors, stop_visualizer
from quality import QUALITY_PROFILES, SoundQuality, get_profile, list_qualities
from random_patch import random_patch
from sequencer import ArpMode
from session_io import load_session, list_builtin_patterns, save_session
from step_sequencer import BLADE_RUNNER_PATTERNS
from synth_voice import CS80Synth, EnvelopeParams, FilterType, LayerParams, LfoWaveform, SynthParams, Waveform
from wav_export import AudioRecorder

BG_DARK = "#0a0e14"
BG_PANEL = "#121820"
NEON_BLUE = "#00d4ff"
NEON_ORANGE = "#ff6b2b"
NEON_DIM = "#1a3a4a"
TEXT_PRIMARY = "#c8e6f0"
TEXT_DIM = "#5a7a8a"
ACCENT_GREEN = "#39ff14"
KEY_WHITE = "#2a3540"
KEY_BLACK = "#0d1117"
KEY_ACTIVE = "#ff6b2b"
FONT_FAMILY = "Consolas"
FONT_TITLE = (FONT_FAMILY, 14, "bold")
FONT_LABEL = (FONT_FAMILY, 9)
FONT_SMALL = (FONT_FAMILY, 8)

USER_PRESETS_DIR = Path(__file__).parent / "user_presets"
USER_PRESETS_DIR.mkdir(exist_ok=True)


class BladeRunnerScale(tk.Scale):
    def __init__(self, parent, label: str, from_: float, to: float, **kwargs) -> None:
        frame = tk.Frame(parent, bg=BG_PANEL)
        frame.pack(fill=tk.X, padx=8, pady=2)
        tk.Label(frame, text=label, font=FONT_LABEL, fg=TEXT_DIM, bg=BG_PANEL, width=14, anchor="w").pack(side=tk.LEFT)
        # takefocus=0: en Windows los Scale capturan el teclado y bloquean las notas
        kwargs.setdefault("takefocus", 0)
        super().__init__(
            frame, from_=from_, to=to, orient=tk.HORIZONTAL, bg=BG_PANEL, fg=NEON_BLUE,
            troughcolor=NEON_DIM, highlightthickness=0, sliderrelief=tk.FLAT,
            activebackground=NEON_ORANGE, font=FONT_SMALL, length=180, **kwargs,
        )
        self.pack(side=tk.RIGHT, fill=tk.X, expand=True)


class Oscilloscope(tk.Canvas):
    def __init__(self, parent, width=880, height=80, **kwargs) -> None:
        super().__init__(parent, width=width, height=height, bg="#050810", highlightthickness=1,
                         highlightbackground=NEON_DIM, **kwargs)
        self._line = None

    def update_waveform(self, samples) -> None:
        self.delete("all")
        w, h = int(self["width"]), int(self["height"])
        mid = h // 2
        self.create_line(0, mid, w, mid, fill=NEON_DIM, dash=(2, 4))
        if samples is None or len(samples) < 2:
            return
        step = max(1, len(samples) // w)
        pts = []
        for i in range(0, min(len(samples), w * step), step):
            x = i // step
            y = mid - int(float(samples[i]) * (mid - 4))
            pts.extend([x, y])
        if len(pts) >= 4:
            self.create_line(pts, fill=NEON_BLUE, width=1, smooth=True)


class SpectrumAnalyzer(tk.Canvas):
    def __init__(self, parent, width=880, height=60, **kwargs) -> None:
        super().__init__(parent, width=width, height=height, bg="#050810", highlightthickness=1,
                         highlightbackground=NEON_DIM, **kwargs)

    def update_spectrum(self, spec) -> None:
        self.delete("all")
        w, h = int(self["width"]), int(self["height"])
        if spec is None or len(spec) < 4:
            return
        bar_w = max(1, w // len(spec))
        for i, val in enumerate(spec):
            bh = int(float(val) * (h - 4))
            color = NEON_ORANGE if i > len(spec) * 0.7 else NEON_BLUE
            self.create_rectangle(i * bar_w, h - bh, (i + 1) * bar_w - 1, h, fill=color, outline="")


class StepSequencerUI(tk.Frame):
    NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

    def __init__(self, parent, synth: CS80Synth, on_change) -> None:
        super().__init__(parent, bg=BG_PANEL)
        self.synth = synth
        self.on_change = on_change
        self._step_btns: list[tk.Button] = []
        self._build()

    def _note_label(self, note: int) -> str:
        if note < 0:
            return "--"
        return f"{self.NOTE_NAMES[note % 12]}{note // 12 - 1}"

    def _build(self) -> None:
        grid = tk.Frame(self, bg=BG_PANEL)
        grid.pack(padx=8, pady=6)
        for i in range(16):
            btn = tk.Button(
                grid, text=f"{i+1}\n--", font=FONT_SMALL, width=4, height=2,
                bg=NEON_DIM, fg=TEXT_DIM, relief=tk.FLAT,
                command=lambda idx=i: self._toggle(idx),
            )
            btn.grid(row=0, column=i, padx=1, pady=2)
            btn.bind("<Double-Button-1>", lambda e, idx=i: self._cycle_note(idx))
            self._step_btns.append(btn)

        ctrl = tk.Frame(self, bg=BG_PANEL)
        ctrl.pack(fill=tk.X, padx=8, pady=4)
        tk.Label(ctrl, text="Patrón:", font=FONT_LABEL, fg=TEXT_DIM, bg=BG_PANEL).pack(side=tk.LEFT)
        self.pattern_var = tk.StringVar(value=list(BLADE_RUNNER_PATTERNS.keys())[0])
        ttk.Combobox(
            ctrl, textvariable=self.pattern_var, values=list(BLADE_RUNNER_PATTERNS.keys()),
            width=18, state="readonly",
        ).pack(side=tk.LEFT, padx=6)
        tk.Button(ctrl, text="CARGAR", font=FONT_SMALL, bg=NEON_BLUE, fg=BG_DARK, relief=tk.FLAT,
                  command=self._load_pattern).pack(side=tk.LEFT, padx=4)
        tk.Button(ctrl, text="CLEAR", font=FONT_SMALL, bg=NEON_DIM, fg=TEXT_PRIMARY, relief=tk.FLAT,
                  command=self._clear).pack(side=tk.LEFT, padx=4)
        self.refresh()

    def _toggle(self, idx: int) -> None:
        self.synth.step_sequencer.toggle_step(idx)
        self.refresh()
        self.on_change()

    def _cycle_note(self, idx: int) -> None:
        step = self.synth.step_sequencer.pattern.steps[idx]
        step.note = 60 if step.note < 0 else (step.note + 1) if step.note < 84 else 48
        step.enabled = step.note >= 0
        self.refresh()
        self.on_change()

    def _load_pattern(self) -> None:
        name = self.pattern_var.get()
        if name in BLADE_RUNNER_PATTERNS:
            self.synth.step_sequencer.set_pattern(BLADE_RUNNER_PATTERNS[name])
            self.refresh()

    def _clear(self) -> None:
        self.synth.step_sequencer.clear()
        self.refresh()

    def refresh(self) -> None:
        for i, btn in enumerate(self._step_btns):
            step = self.synth.step_sequencer.pattern.steps[i]
            label = f"{i+1}\n{self._note_label(step.note)}"
            bg = KEY_ACTIVE if step.enabled and step.accent else (NEON_BLUE if step.enabled else NEON_DIM)
            fg = BG_DARK if step.enabled else TEXT_DIM
            btn.config(text=label, bg=bg, fg=fg)


class QualityLadder(tk.Frame):
    """
    Selector de calidad: Básica → Profesional.
    Aspecto de medidor neón — un clic, sin jerga técnica.
    """

    def __init__(self, parent, on_change, initial: SoundQuality = SoundQuality.STANDARD) -> None:
        super().__init__(parent, bg=BG_DARK)
        self.on_change = on_change
        self.level = int(initial)
        self._btns: list[tk.Button] = []
        self._build()

    def _build(self) -> None:
        top = tk.Frame(self, bg=BG_DARK)
        top.pack(fill=tk.X)
        tk.Label(
            top, text="CALIDAD", font=FONT_SMALL, fg=TEXT_DIM, bg=BG_DARK,
        ).pack(side=tk.LEFT, padx=(0, 10))

        rail = tk.Frame(top, bg=BG_DARK)
        rail.pack(side=tk.LEFT, fill=tk.X, expand=True)

        profiles = list_qualities()
        for i, profile in enumerate(profiles):
            btn = tk.Button(
                rail,
                text=profile.label.upper(),
                font=(FONT_FAMILY, 8, "bold"),
                relief=tk.FLAT,
                bd=0,
                padx=10,
                pady=4,
                cursor="hand2",
                takefocus=0,
                command=lambda idx=i: self.set_level(idx, notify=True),
            )
            btn.pack(side=tk.LEFT, padx=2)
            self._btns.append(btn)
            if i < len(profiles) - 1:
                tk.Label(rail, text="·", font=FONT_SMALL, fg=NEON_DIM, bg=BG_DARK).pack(side=tk.LEFT)

        self.hint = tk.Label(self, text="", font=FONT_SMALL, fg=TEXT_DIM, bg=BG_DARK, anchor="w")
        self.hint.pack(fill=tk.X, pady=(4, 0))
        self._refresh()

    def set_level(self, level: int, notify: bool = False) -> None:
        self.level = max(0, min(4, int(level)))
        self._refresh()
        if notify:
            self.on_change(SoundQuality(self.level))

    def _refresh(self) -> None:
        profiles = list_qualities()
        for i, btn in enumerate(self._btns):
            profile = profiles[i]
            active = i == self.level
            if active:
                btn.config(bg=profile.color, fg=BG_DARK, activebackground=profile.color)
            else:
                btn.config(bg=NEON_DIM, fg=TEXT_DIM, activebackground=NEON_ORANGE, activeforeground=BG_DARK)
        profile = profiles[self.level]
        rate_k = profile.sample_rate / 1000.0
        self.hint.config(
            text=f"  {profile.hint}   ·   {rate_k:g} kHz  ·  buffer {profile.block_size}",
            fg=profile.color,
        )


def show_splash(root: tk.Tk) -> None:
    splash = tk.Toplevel(root)
    splash.overrideredirect(True)
    splash.configure(bg=BG_DARK)
    sw, sh = 480, 200
    x = root.winfo_screenwidth() // 2 - sw // 2
    y = root.winfo_screenheight() // 2 - sh // 2
    splash.geometry(f"{sw}x{sh}+{x}+{y}")
    tk.Label(splash, text="YAMAHA CS-80", font=(FONT_FAMILY, 22, "bold"), fg=NEON_BLUE, bg=BG_DARK).pack(pady=(30, 4))
    tk.Label(splash, text="BLADE RUNNER EDITION  v3", font=FONT_LABEL, fg=NEON_ORANGE, bg=BG_DARK).pack()
    tk.Label(splash, text='"All those moments will be lost in time..."', font=FONT_SMALL, fg=TEXT_DIM, bg=BG_DARK).pack(pady=16)
    tk.Label(splash, text="like tears in rain", font=FONT_SMALL, fg=NEON_BLUE, bg=BG_DARK).pack()
    splash.after(2200, splash.destroy)


class PianoKeyboard(tk.Frame):
    WHITE_KEYS = [0, 2, 4, 5, 7, 9, 11]
    BLACK_OFFSETS = {1: 0, 3: 1, 6: 2, 8: 3, 10: 4}

    def __init__(self, parent, on_note_on, on_note_off, start_octave=3, num_octaves=2) -> None:
        super().__init__(parent, bg=BG_PANEL)
        self.on_note_on = on_note_on
        self.on_note_off = on_note_off
        self.start_octave = start_octave
        self.num_octaves = num_octaves
        self._buttons: dict[int, tk.Button] = {}
        self._build()

    def _build(self) -> None:
        white_w, white_h, black_w, black_h = 32, 72, 20, 44
        x = 0
        for oct_ in range(self.num_octaves):
            for semi in self.WHITE_KEYS:
                note = (self.start_octave + oct_) * 12 + semi
                btn = tk.Button(
                    self, bg=KEY_WHITE, activebackground=KEY_ACTIVE, relief=tk.FLAT,
                    borderwidth=1, highlightthickness=0, width=2, height=3,
                    takefocus=0, command=lambda n=note: None,
                )
                btn.place(x=x, y=0, width=white_w, height=white_h)
                btn.bind("<ButtonPress-1>", lambda e, n=note: self._press(n))
                btn.bind("<ButtonRelease-1>", lambda e, n=note: self._release(n))
                self._buttons[note] = btn
                x += white_w

            base_x = oct_ * len(self.WHITE_KEYS) * white_w
            for semi, off in self.BLACK_OFFSETS.items():
                note = (self.start_octave + oct_) * 12 + semi
                btn = tk.Button(
                    self, bg=KEY_BLACK, activebackground=KEY_ACTIVE, relief=tk.FLAT,
                    borderwidth=0, highlightthickness=0, width=1, height=2, takefocus=0,
                )
                btn.place(x=base_x + off * white_w + white_w - black_w // 2, y=0, width=black_w, height=black_h)
                btn.bind("<ButtonPress-1>", lambda e, n=note: self._press(n))
                btn.bind("<ButtonRelease-1>", lambda e, n=note: self._release(n))
                self._buttons[note] = btn

        self.config(width=x, height=white_h + 4)

    def _press(self, note: int) -> None:
        if note in self._buttons:
            self._buttons[note].config(bg=KEY_ACTIVE)
        self.on_note_on(note, 100)

    def _release(self, note: int) -> None:
        if note in self._buttons:
            semi = note % 12
            color = KEY_BLACK if semi in self.BLACK_OFFSETS else KEY_WHITE
            self._buttons[note].config(bg=color)
        self.on_note_off(note)


class CS80GUI:
    # keysym en minúsculas (Windows/Linux) + aliases
    KEY_MAP = {
        "z": 48, "s": 49, "x": 50, "d": 51, "c": 52, "v": 53, "g": 54, "b": 55,
        "h": 56, "n": 57, "j": 58, "m": 59,
        "comma": 60, "less": 60, ",": 60,
        "q": 60, "2": 61, "w": 62, "3": 63, "e": 64, "r": 65, "5": 66, "t": 67,
        "6": 68, "y": 69, "7": 70, "u": 71, "i": 72,
    }

    WAVE_OPTIONS = [w.value for w in Waveform]
    FILTER_OPTIONS = [f.value for f in FilterType]
    ARP_OPTIONS = [m.value for m in ArpMode]

    def __init__(
        self,
        synth: CS80Synth,
        engine: AudioEngine,
        recorder: Optional[AudioRecorder] = None,
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
        self.synth = synth
        self.engine = engine
        self.recorder = recorder or AudioRecorder(SAMPLE_RATE)
        self.on_close = on_close
        self._keys_pressed: set[str] = set()
        self._sliders: dict[str, BladeRunnerScale] = {}
        self._viz = None
        self._viz_bus = None

        self.root = tk.Tk()
        self.root.title("YAMAHA CS-80  //  BLADE RUNNER SYNTH  v3")
        self.root.configure(bg=BG_DARK)
        self._fit_to_screen()
        self.root.protocol("WM_DELETE_WINDOW", self._handle_close)

        show_splash(self.root)
        self._build_ui()
        self._bind_keys()
        self._sync_from_params(self.synth.params)
        self._animate_scope()
        self.root.after(100, self._focus_root)

    def _fit_to_screen(self) -> None:
        """Ajusta tamaño a la resolución disponible (deja margen para barra de tareas)."""
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = min(980, max(720, sw - 40))
        h = min(820, max(520, sh - 80))
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.minsize(640, 480)
        # Maximizar solo en monitores grandes
        if sw >= 1400 and sh >= 900:
            try:
                self.root.state("zoomed")
            except tk.TclError:
                pass

    def _focus_root(self) -> None:
        try:
            self.root.focus_force()
            self.root.lift()
        except tk.TclError:
            pass

    def _build_scrollable_tab(self, notebook: ttk.Notebook, title: str) -> tk.Frame:
        """Pestaña con scroll vertical para pantallas pequeñas."""
        outer = tk.Frame(notebook, bg=BG_PANEL)
        notebook.add(outer, text=title)
        canvas = tk.Canvas(outer, bg=BG_PANEL, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG_PANEL)
        inner.bind(
            "<Configure>",
            lambda e, c=canvas: c.configure(scrollregion=c.bbox("all")),
        )
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind(
            "<Configure>",
            lambda e, c=canvas, w=win: c.itemconfigure(w, width=e.width),
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_mousewheel(event, c=canvas):
            delta = -1 if event.delta > 0 else 1
            if hasattr(event, "num") and event.num in (4, 5):
                delta = -1 if event.num == 4 else 1
            c.yview_scroll(delta, "units")

        canvas.bind("<Enter>", lambda e, c=canvas: c.bind_all("<MouseWheel>", lambda ev: _on_mousewheel(ev, c)))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        return inner

    def _build_ui(self) -> None:
        header = tk.Frame(self.root, bg=BG_DARK)
        header.pack(fill=tk.X, padx=12, pady=(6, 2))
        tk.Label(header, text="◈  CS-80 SIMULATOR  v3", font=FONT_TITLE, fg=NEON_BLUE, bg=BG_DARK).pack(side=tk.LEFT)
        tk.Label(header, text="NEXUS-6 AUDIO LAB  //  2019", font=FONT_SMALL, fg=NEON_ORANGE, bg=BG_DARK).pack(side=tk.RIGHT)
        tk.Frame(self.root, bg=NEON_BLUE, height=1).pack(fill=tk.X, padx=12, pady=2)

        self.scope = Oscilloscope(self.root, height=48)
        self.scope.pack(fill=tk.X, padx=12, pady=(0, 2))
        self.spectrum = SpectrumAnalyzer(self.root, height=36)
        self.spectrum.pack(fill=tk.X, padx=12, pady=(0, 4))

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=2)

        tab_synth = self._build_scrollable_tab(notebook, " SYNTH ")
        tab_layer2 = self._build_scrollable_tab(notebook, " LAYER II ")
        tab_fx = self._build_scrollable_tab(notebook, " FX ")
        tab_arp = self._build_scrollable_tab(notebook, " ARP ")
        tab_seq = self._build_scrollable_tab(notebook, " SEQ ")
        tab_misc = self._build_scrollable_tab(notebook, " MISC ")

        left = tk.Frame(tab_synth, bg=BG_PANEL)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right = tk.Frame(tab_synth, bg=BG_PANEL)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self._build_osc_panel(left)
        self._build_filter_panel(left)
        self._build_env_panel(right)
        self._build_lfo_panel(right)
        self._build_mod_panel(right)
        self._build_layer2_panel(tab_layer2)
        self._build_fx_panel(tab_fx)
        self._build_arp_panel(tab_arp)
        self._build_seq_panel(tab_seq)
        self._build_misc_panel(tab_misc)
        self._build_preset_panel(self.root)
        self._build_quality_panel(self.root)
        self._build_transport(self.root)
        self._build_piano(self.root)

        self.status_label = tk.Label(
            self.root,
            text="[ AUDIO OFF ]  Z-M / Q-I = teclado  |  START AUDIO primero",
            font=FONT_SMALL,
            fg=TEXT_DIM,
            bg=BG_DARK,
        )
        self.status_label.pack(fill=tk.X, padx=12, pady=(2, 6))

    def _section_title(self, parent, text: str) -> None:
        tk.Label(parent, text=text, font=FONT_LABEL, fg=NEON_ORANGE, bg=BG_PANEL, anchor="w").pack(fill=tk.X, padx=8, pady=(8, 2))

    def _add_slider(self, parent, key, label, from_, to, resolution=0.01, callback=None) -> BladeRunnerScale:
        scale = BladeRunnerScale(parent, label, from_, to, resolution=resolution, command=callback or self._on_param_change)
        self._sliders[key] = scale
        return scale

    def _add_combo(self, parent, label, var, values, callback=None) -> None:
        frame = tk.Frame(parent, bg=BG_PANEL)
        frame.pack(fill=tk.X, padx=8, pady=3)
        tk.Label(frame, text=label, font=FONT_LABEL, fg=TEXT_DIM, bg=BG_PANEL, width=14, anchor="w").pack(side=tk.LEFT)
        ttk.Combobox(frame, textvariable=var, values=values, width=12, state="readonly").pack(side=tk.RIGHT)
        var.trace_add("write", lambda *_: (callback or self._on_param_change)())

    def _build_osc_panel(self, parent) -> None:
        self._section_title(parent, "▸ OSCILADORES (Layer I)")
        self._add_slider(parent, "osc_mix", "Osc Mix", 0.0, 1.0)
        self._add_slider(parent, "volume", "Volume", 0.0, 1.0)
        self.osc1_var = tk.StringVar(value=Waveform.SAW.value)
        self.osc2_var = tk.StringVar(value=Waveform.SQUARE.value)
        self._add_combo(parent, "Osc 1 Wave", self.osc1_var, self.WAVE_OPTIONS)
        self._add_combo(parent, "Osc 2 Wave", self.osc2_var, self.WAVE_OPTIONS)

    def _build_filter_panel(self, parent) -> None:
        self._section_title(parent, "▸ FILTRO")
        self.filter_var = tk.StringVar(value=FilterType.LOWPASS.value)
        self._add_combo(parent, "Filter Type", self.filter_var, self.FILTER_OPTIONS)
        self._add_slider(parent, "cutoff", "Cutoff Hz", 200.0, 8000.0, resolution=10.0)
        self._add_slider(parent, "resonance", "Resonance", 0.0, 0.95)
        self._add_slider(parent, "filter_env_amount", "F.Env Amt", 0.0, 1.0)

    def _build_env_panel(self, parent) -> None:
        self._section_title(parent, "▸ AMP ENVELOPE")
        for k, lbl in [("amp_attack", "Attack"), ("amp_decay", "Decay"), ("amp_sustain", "Sustain"), ("amp_release", "Release")]:
            self._add_slider(parent, k, lbl, 0.001 if "attack" in k else 0.01, 3.0)
        self._section_title(parent, "▸ FILTER ENVELOPE")
        for k, lbl in [("filt_attack", "F.Attack"), ("filt_decay", "F.Decay"), ("filt_sustain", "F.Sustain"), ("filt_release", "F.Release")]:
            self._add_slider(parent, k, lbl, 0.001 if "attack" in k else 0.01, 3.0)

    def _build_lfo_panel(self, parent) -> None:
        self._section_title(parent, "▸ LFO")
        self._add_slider(parent, "lfo_rate", "LFO Rate Hz", 0.1, 15.0)
        self._add_slider(parent, "lfo_depth", "Vibrato", 0.0, 1.0)
        self._add_slider(parent, "lfo_filter_depth", "Filter LFO", 0.0, 1.0)
        self._add_slider(parent, "pitch_bend", "Pitch Bend", -7.0, 7.0)
        self.lfo_wave_var = tk.StringVar(value=LfoWaveform.SINE.value)
        self._add_combo(parent, "LFO Wave", self.lfo_wave_var, [w.value for w in LfoWaveform])
        self._add_slider(parent, "lfo_tremolo", "Tremolo", 0.0, 1.0)

    def _build_mod_panel(self, parent) -> None:
        self._section_title(parent, "▸ MODULACIÓN")
        self._add_slider(parent, "ring_mod", "Ring Mod", 0.0, 1.0)
        self._add_slider(parent, "sub_osc", "Sub Osc", 0.0, 1.0)
        self._add_slider(parent, "aftertouch", "Aftertouch", 0.0, 1.0)

    def _build_layer2_panel(self, parent) -> None:
        self._section_title(parent, "▸ CAPA II (Dual Layer CS-80)")
        self.layer2_enabled = tk.BooleanVar(value=False)
        tk.Checkbutton(
            parent, text="Activar Layer II", variable=self.layer2_enabled, font=FONT_LABEL,
            fg=NEON_BLUE, bg=BG_PANEL, selectcolor=BG_DARK, activebackground=BG_PANEL,
            command=self._on_param_change,
        ).pack(anchor="w", padx=8, pady=4)
        self._add_slider(parent, "layer2_mix", "Layer II Mix", 0.0, 1.0)
        self._add_slider(parent, "l2_detune", "Detune cents", -50.0, 50.0, resolution=1.0)
        self._add_slider(parent, "l2_level", "Layer II Level", 0.0, 1.0)
        self.l2_osc1_var = tk.StringVar(value=Waveform.SINE.value)
        self.l2_osc2_var = tk.StringVar(value=Waveform.SAW.value)
        self._add_combo(parent, "L2 Osc 1", self.l2_osc1_var, self.WAVE_OPTIONS)
        self._add_combo(parent, "L2 Osc 2", self.l2_osc2_var, self.WAVE_OPTIONS)
        self._add_slider(parent, "l2_osc_mix", "L2 Osc Mix", 0.0, 1.0)

    def _build_fx_panel(self, parent) -> None:
        self._section_title(parent, "▸ DELAY")
        self._add_slider(parent, "delay_time", "Time sec", 0.05, 1.5)
        self._add_slider(parent, "delay_fb", "Feedback", 0.0, 0.9)
        self._add_slider(parent, "delay_mix", "Delay Mix", 0.0, 1.0)
        self._section_title(parent, "▸ REVERB")
        self._add_slider(parent, "reverb_size", "Size", 0.1, 0.99)
        self._add_slider(parent, "reverb_mix", "Reverb Mix", 0.0, 1.0)
        self._section_title(parent, "▸ CHORUS")
        self._add_slider(parent, "chorus_rate", "Rate Hz", 0.1, 3.0)
        self._add_slider(parent, "chorus_depth", "Depth", 0.0, 0.01, resolution=0.0001)
        self._add_slider(parent, "chorus_mix", "Chorus Mix", 0.0, 1.0)
        self._section_title(parent, "▸ BITCRUSHER")
        self._add_slider(parent, "bitcrush_bits", "Bits", 4.0, 16.0, resolution=1.0)
        self._add_slider(parent, "bitcrush_mix", "Crush Mix", 0.0, 1.0)

    def _build_seq_panel(self, parent) -> None:
        self._section_title(parent, "▸ SECUENCIADOR 16 PASOS")
        self.seq_enabled = tk.BooleanVar(value=False)
        tk.Checkbutton(
            parent, text="Activar Secuenciador", variable=self.seq_enabled, font=FONT_LABEL,
            fg=NEON_BLUE, bg=BG_PANEL, selectcolor=BG_DARK, activebackground=BG_PANEL,
            command=self._on_param_change,
        ).pack(anchor="w", padx=8, pady=4)
        self._add_slider(parent, "seq_bpm", "BPM", 40.0, 200.0, resolution=1.0)
        self._add_slider(parent, "seq_swing", "Swing", 0.0, 1.0)
        self.seq_ui = StepSequencerUI(parent, self.synth, self._on_param_change)
        self.seq_ui.pack(fill=tk.X)

    def _build_misc_panel(self, parent) -> None:
        self._section_title(parent, "▸ PERFORMANCE")
        self._add_slider(parent, "portamento", "Portamento s", 0.0, 0.5)
        self._add_slider(parent, "ribbon", "Ribbon Ctrl", -1.0, 1.0)
        self._add_slider(parent, "pan", "Pan", -1.0, 1.0)
        self._add_slider(parent, "stereo_width", "Stereo Width", 0.0, 1.0)
        self._add_slider(parent, "unison", "Unison", 0.0, 1.0)
        self._section_title(parent, "▸ HERRAMIENTAS")
        tools = tk.Frame(parent, bg=BG_PANEL)
        tools.pack(fill=tk.X, padx=8, pady=8)
        for text, cmd in [
            ("RANDOMIZE", self._randomize),
            ("SAVE SESSION", self._save_session),
            ("LOAD SESSION", self._load_session),
        ]:
            tk.Button(tools, text=text, font=FONT_LABEL, fg=BG_DARK, bg=NEON_ORANGE,
                      relief=tk.FLAT, padx=10, pady=4, command=cmd).pack(side=tk.LEFT, padx=4)

    def _build_arp_panel(self, parent) -> None:
        self._section_title(parent, "▸ ARPEGGIATOR")
        self.arp_enabled = tk.BooleanVar(value=False)
        tk.Checkbutton(
            parent, text="Activar Arpegiador", variable=self.arp_enabled, font=FONT_LABEL,
            fg=NEON_BLUE, bg=BG_PANEL, selectcolor=BG_DARK, activebackground=BG_PANEL,
            command=self._on_param_change,
        ).pack(anchor="w", padx=8, pady=4)
        self._add_slider(parent, "arp_rate", "Rate Hz", 0.5, 16.0)
        self._add_slider(parent, "arp_octaves", "Octaves", 1, 3, resolution=1.0)
        self.arp_mode_var = tk.StringVar(value=ArpMode.UP.value)
        self._add_combo(parent, "Arp Mode", self.arp_mode_var, self.ARP_OPTIONS)

    def _build_preset_panel(self, parent) -> None:
        frame = tk.Frame(parent, bg=BG_DARK)
        frame.pack(fill=tk.X, padx=16, pady=4)
        tk.Label(frame, text="PRESET:", font=FONT_LABEL, fg=TEXT_DIM, bg=BG_DARK).pack(side=tk.LEFT)
        self.preset_var = tk.StringVar(value=list_presets()[0])
        ttk.Combobox(frame, textvariable=self.preset_var, values=list_presets(), width=24, state="readonly").pack(side=tk.LEFT, padx=8)
        for text, cmd in [("LOAD", self._load_preset), ("SAVE", self._save_preset), ("DEMO", self._play_demo), ("SEQ DEMO", self._play_seq_demo)]:
            tk.Button(frame, text=text, font=FONT_LABEL, fg=BG_DARK, bg=NEON_BLUE, relief=tk.FLAT, padx=10, command=cmd).pack(side=tk.LEFT, padx=3)

    def _build_quality_panel(self, parent) -> None:
        frame = tk.Frame(parent, bg=BG_DARK, highlightbackground=NEON_DIM, highlightthickness=1)
        frame.pack(fill=tk.X, padx=12, pady=(2, 6))
        inner = tk.Frame(frame, bg=BG_DARK)
        inner.pack(fill=tk.X, padx=10, pady=8)
        initial = getattr(self.synth, "quality", get_profile(SoundQuality.STANDARD)).level
        self.quality_ladder = QualityLadder(inner, self._on_quality_change, initial=initial)
        self.quality_ladder.pack(fill=tk.X)

    def _on_quality_change(self, level: SoundQuality) -> None:
        was_running = self.engine.is_running
        if was_running:
            self.engine.stop()
            self.synth.all_notes_off()

        profile = self.synth.apply_quality(level)
        try:
            self.engine.configure(profile.sample_rate, profile.block_size)
        except Exception as exc:
            # Fallback si el dispositivo no soporta 96 kHz, etc.
            fallback = get_profile(SoundQuality.HIGH if level > SoundQuality.HIGH else SoundQuality.STANDARD)
            self.synth.apply_quality(fallback.level)
            self.engine.configure(fallback.sample_rate, fallback.block_size)
            self.quality_ladder.set_level(int(fallback.level), notify=False)
            self.status_label.config(text=f"[ CALIDAD ]  Dispositivo no soporta {profile.label} → {fallback.label}  ({exc})")
            if was_running:
                self.engine.start(self._audio_callback)
                self.audio_btn.config(text="■  STOP AUDIO", bg=NEON_ORANGE)
            return

        if was_running:
            self.engine.start(self._audio_callback)
            self.audio_btn.config(text="■  STOP AUDIO", bg=NEON_ORANGE)
            self.status_label.config(text=f"[ CALIDAD ]  {profile.label}  ·  audio reiniciado")
        else:
            self.status_label.config(text=f"[ CALIDAD ]  {profile.label}  ·  lista al iniciar audio")

    def _build_transport(self, parent) -> None:
        transport = tk.Frame(parent, bg=BG_DARK)
        transport.pack(fill=tk.X, padx=16, pady=4)
        self.audio_btn = tk.Button(
            transport, text="▶  START AUDIO", font=FONT_LABEL, fg=BG_DARK, bg=ACCENT_GREEN,
            relief=tk.FLAT, padx=16, pady=6, command=self._toggle_audio,
        )
        self.audio_btn.pack(side=tk.LEFT)
        self.record_btn = tk.Button(
            transport, text="●  REC", font=FONT_LABEL, fg=BG_DARK, bg=NEON_ORANGE,
            relief=tk.FLAT, padx=12, pady=6, command=self._toggle_record,
        )
        self.record_btn.pack(side=tk.LEFT, padx=6)
        tk.Button(
            transport, text="💾  EXPORT WAV", font=FONT_LABEL, fg=TEXT_PRIMARY, bg=NEON_DIM,
            relief=tk.FLAT, padx=12, pady=6, command=self._export_wav,
        ).pack(side=tk.LEFT, padx=4)
        tk.Button(
            transport, text="■  ALL OFF", font=FONT_LABEL, fg=TEXT_PRIMARY, bg=NEON_DIM,
            relief=tk.FLAT, padx=12, pady=6, command=self.synth.all_notes_off,
        ).pack(side=tk.LEFT, padx=4)
        self.viz_btn = tk.Button(
            transport, text="◈  VIZ GL", font=FONT_LABEL, fg=BG_DARK, bg=NEON_BLUE,
            relief=tk.FLAT, padx=12, pady=6, command=self._toggle_visualizer,
        )
        self.viz_btn.pack(side=tk.RIGHT, padx=4)
        self._viz_monitors = list_monitors() if OPENGL_OK else []
        mon_labels = [m.label for m in self._viz_monitors] or ["Monitor 1"]
        self._viz_monitor_var = tk.StringVar(value=mon_labels[0])
        self.viz_monitor_combo = ttk.Combobox(
            transport,
            textvariable=self._viz_monitor_var,
            values=mon_labels,
            state="readonly",
            width=28,
            font=FONT_SMALL,
        )
        self.viz_monitor_combo.pack(side=tk.RIGHT, padx=4)
        tk.Label(
            transport, text="VIZ →", font=FONT_SMALL, fg=TEXT_DIM, bg=BG_DARK,
        ).pack(side=tk.RIGHT)

    def _build_piano(self, parent) -> None:
        frame = tk.Frame(parent, bg=BG_DARK)
        frame.pack(fill=tk.X, padx=12, pady=2)
        tk.Label(frame, text="▸ PIANO  (clic o Z-M / Q-I)", font=FONT_LABEL, fg=NEON_ORANGE, bg=BG_DARK).pack(anchor="w")
        self.piano = PianoKeyboard(frame, self._piano_note_on, self._piano_note_off, start_octave=3, num_octaves=2)
        self.piano.pack(pady=2)

    def _piano_note_on(self, note: int, vel: int) -> None:
        if self.engine.is_running:
            self.synth.note_on(note, vel)

    def _piano_note_off(self, note: int) -> None:
        self.synth.note_off(note)

    def _params_to_dict(self, params: SynthParams) -> dict:
        return {
            "layer1_osc1": params.layer1.osc1_wave.value,
            "layer1_osc2": params.layer1.osc2_wave.value,
            "osc_mix": params.layer1.osc_mix,
            "layer2_enabled": params.layer2_enabled,
            "layer2_mix": params.layer2_mix,
            "l2_osc1": params.layer2.osc1_wave.value,
            "l2_osc2": params.layer2.osc2_wave.value,
            "l2_osc_mix": params.layer2.osc_mix,
            "l2_detune": params.layer2.detune_cents,
            "l2_level": params.layer2.level,
            "filter_type": params.filter_type.value,
            "cutoff": params.cutoff,
            "resonance": params.resonance,
            "filter_env_amount": params.filter_env_amount,
            "lfo_rate": params.lfo_rate,
            "lfo_depth": params.lfo_depth,
            "lfo_filter_depth": params.lfo_filter_depth,
            "volume": params.volume,
            "pitch_bend": params.pitch_bend,
            "ring_mod": params.ring_mod_amount,
            "sub_osc": params.sub_osc_level,
            "aftertouch": params.aftertouch_depth,
            "delay_time": params.effects.delay_time,
            "delay_fb": params.effects.delay_feedback,
            "delay_mix": params.effects.delay_mix,
            "reverb_size": params.effects.reverb_size,
            "reverb_mix": params.effects.reverb_mix,
            "chorus_rate": params.effects.chorus_rate,
            "chorus_depth": params.effects.chorus_depth,
            "chorus_mix": params.effects.chorus_mix,
            "bitcrush_bits": params.effects.bitcrush_bits,
            "bitcrush_mix": params.effects.bitcrush_mix,
            "lfo_wave": params.lfo_wave.value,
            "lfo_tremolo": params.lfo_tremolo,
            "portamento": params.portamento,
            "ribbon": params.ribbon,
            "pan": params.pan,
            "stereo_width": params.stereo_width,
            "unison": params.unison,
            "seq_enabled": params.seq_enabled,
            "seq_bpm": params.seq_bpm,
            "seq_swing": params.seq_swing,
            "arp_enabled": params.arp_enabled,
            "arp_rate": params.arp_rate,
            "arp_mode": params.arp_mode.value,
            "arp_octaves": params.arp_octaves,
            "amp_attack": params.amp_env.attack,
            "amp_decay": params.amp_env.decay,
            "amp_sustain": params.amp_env.sustain,
            "amp_release": params.amp_env.release,
            "filt_attack": params.filter_env.attack,
            "filt_decay": params.filter_env.decay,
            "filt_sustain": params.filter_env.sustain,
            "filt_release": params.filter_env.release,
        }

    def _sync_from_params(self, params: SynthParams) -> None:
        data = self._params_to_dict(params)
        skip = {"layer1_osc1", "layer1_osc2", "l2_osc1", "l2_osc2", "filter_type", "arp_mode",
                "layer2_enabled", "arp_enabled", "lfo_wave", "seq_enabled"}
        for key, value in data.items():
            if key in skip:
                continue
            if key in self._sliders:
                self._sliders[key].set(value)
        self.osc1_var.set(params.layer1.osc1_wave.value)
        self.osc2_var.set(params.layer1.osc2_wave.value)
        self.l2_osc1_var.set(params.layer2.osc1_wave.value)
        self.l2_osc2_var.set(params.layer2.osc2_wave.value)
        self.filter_var.set(params.filter_type.value)
        self.arp_mode_var.set(params.arp_mode.value)
        self.layer2_enabled.set(params.layer2_enabled)
        self.arp_enabled.set(params.arp_enabled)
        self.lfo_wave_var.set(params.lfo_wave.value)
        self.seq_enabled.set(params.seq_enabled)
        if hasattr(self, "seq_ui"):
            self.seq_ui.refresh()

    def _collect_params(self) -> SynthParams:
        s = self._sliders
        return SynthParams(
            layer1=LayerParams(Waveform(self.osc1_var.get()), Waveform(self.osc2_var.get()), s["osc_mix"].get()),
            layer2=LayerParams(
                Waveform(self.l2_osc1_var.get()), Waveform(self.l2_osc2_var.get()),
                s["l2_osc_mix"].get(), s["l2_detune"].get(), s["l2_level"].get(),
            ),
            layer2_enabled=self.layer2_enabled.get(),
            layer2_mix=s["layer2_mix"].get(),
            cutoff=s["cutoff"].get(),
            resonance=s["resonance"].get(),
            filter_type=FilterType(self.filter_var.get()),
            filter_env_amount=s["filter_env_amount"].get(),
            lfo_rate=s["lfo_rate"].get(),
            lfo_depth=s["lfo_depth"].get(),
            lfo_filter_depth=s["lfo_filter_depth"].get(),
            lfo_wave=LfoWaveform(self.lfo_wave_var.get()),
            lfo_tremolo=s["lfo_tremolo"].get(),
            volume=s["volume"].get(),
            pitch_bend=s["pitch_bend"].get(),
            ribbon=s["ribbon"].get(),
            pan=s["pan"].get(),
            portamento=s["portamento"].get(),
            unison=s["unison"].get(),
            stereo_width=s["stereo_width"].get(),
            ring_mod_amount=s["ring_mod"].get(),
            sub_osc_level=s["sub_osc"].get(),
            aftertouch_depth=s["aftertouch"].get(),
            amp_env=EnvelopeParams(s["amp_attack"].get(), s["amp_decay"].get(), s["amp_sustain"].get(), s["amp_release"].get()),
            filter_env=EnvelopeParams(s["filt_attack"].get(), s["filt_decay"].get(), s["filt_sustain"].get(), s["filt_release"].get()),
            effects=EffectParams(
                s["delay_time"].get(), s["delay_fb"].get(), s["delay_mix"].get(),
                s["reverb_size"].get(), s["reverb_mix"].get(),
                s["chorus_rate"].get(), s["chorus_depth"].get(), s["chorus_mix"].get(),
                s["bitcrush_bits"].get(), s["bitcrush_mix"].get(),
            ),
            arp_enabled=self.arp_enabled.get(),
            arp_rate=s["arp_rate"].get(),
            arp_mode=ArpMode(self.arp_mode_var.get()),
            arp_octaves=int(s["arp_octaves"].get()),
            seq_enabled=self.seq_enabled.get(),
            seq_bpm=s["seq_bpm"].get(),
            seq_swing=s["seq_swing"].get(),
        )

    def _on_param_change(self, *_args) -> None:
        self.synth.apply_params(self._collect_params())

    def _load_preset(self) -> None:
        name = self.preset_var.get()
        params = load_preset(name, self.synth)
        self._sync_from_params(params)
        self.status_label.config(text=f"[ PRESET ]  {name}")

    def _save_preset(self) -> None:
        name = self.preset_var.get().strip() or "custom"
        path = USER_PRESETS_DIR / f"{name.replace(' ', '_')}.json"
        path.write_text(json.dumps(self._params_to_dict(self._collect_params()), indent=2), encoding="utf-8")
        messagebox.showinfo("Preset", f"Guardado:\n{path}")

    def _randomize(self) -> None:
        params = random_patch()
        self.synth.apply_params(params)
        self._sync_from_params(params)
        self.status_label.config(text="[ RANDOM ]  Parche aleatorio generado")

    def _save_session(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Session", "*.json")])
        if path:
            save_session(path, self.synth, self.preset_var.get())
            messagebox.showinfo("Session", f"Sesión guardada:\n{path}")

    def _load_session(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Session", "*.json")])
        if path:
            load_session(path, self.synth)
            self._sync_from_params(self.synth.params)
            messagebox.showinfo("Session", f"Sesión cargada:\n{path}")

    def _play_seq_demo(self) -> None:
        if not self.engine.is_running:
            self._toggle_audio()
        name = "BR Main Theme"
        if name in BLADE_RUNNER_PATTERNS:
            self.synth.step_sequencer.set_pattern(BLADE_RUNNER_PATTERNS[name])
            self.seq_ui.refresh()
        self.seq_enabled.set(True)
        params = self._collect_params()
        params.seq_enabled = True
        self.synth.apply_params(params)
        self.status_label.config(text=f"[ SEQ ]  Reproduciendo: {name}")

    def _play_demo(self) -> None:
        if not self.engine.is_running:
            self._toggle_audio()
        demo = [(0, "on", 60), (22050, "on", 64), (44100, "on", 67), (66150, "on", 72),
                (110250, "off", 60), (110250, "off", 64), (110250, "off", 67), (110250, "off", 72)]
        self.status_label.config(text="[ DEMO ]  Secuencia Blade Runner...")
        for i, (_, action, note) in enumerate(demo):
            delay = 500 if i > 0 else 0
            self.root.after(int(delay), lambda a=action, n=note: (
                self.synth.note_on(n, 90) if a == "on" else self.synth.note_off(n)
            ))

    def _audio_callback(self, frames: int):
        samples = self.synth.render(frames)
        self.recorder.feed(samples)
        return samples

    def _toggle_audio(self) -> None:
        if self.engine.is_running:
            self.engine.stop()
            self.synth.all_notes_off()
            self.audio_btn.config(text="▶  START AUDIO", bg=ACCENT_GREEN)
            self.status_label.config(text="[ AUDIO OFF ]")
        else:
            self.engine.start(self._audio_callback)
            self.audio_btn.config(text="■  STOP AUDIO", bg=NEON_ORANGE)
            self.status_label.config(text="[ AUDIO ON ]")

    def _toggle_record(self) -> None:
        if self.recorder.recording:
            self.recorder.stop()
            self.record_btn.config(text="●  REC", bg=NEON_ORANGE)
            self.status_label.config(text=f"[ REC STOP ]  {self.recorder.duration:.1f}s grabados")
        else:
            if not self.engine.is_running:
                self._toggle_audio()
            self.recorder.start()
            self.record_btn.config(text="■  STOP REC", bg="#ff0040")
            self.status_label.config(text="[ REC ]  Grabando...")

    def _export_wav(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".wav", filetypes=[("WAV", "*.wav")])
        if not path:
            return
        try:
            out = self.recorder.export_wav(path)
            messagebox.showinfo("Export", f"Exportado:\n{out}\n({self.recorder.duration:.1f}s)")
        except ValueError as exc:
            messagebox.showerror("Export", str(exc))

    def _toggle_visualizer(self) -> None:
        if self._viz is not None and self._viz.is_running:
            stop_visualizer()
            self._viz = None
            self._viz_bus = None
            self.viz_btn.config(text="◈  VIZ GL", bg=NEON_BLUE)
            self.status_label.config(text="[ VIZ ]  Ventana OpenGL cerrada")
            return

        if not OPENGL_OK:
            messagebox.showerror(
                "OpenGL",
                "Faltan dependencias.\n\npip install pygame PyOpenGL PyOpenGL-accelerate",
            )
            return

        def _on_viz_close() -> None:
            self.root.after(0, self._viz_closed_from_thread)

        # Refrescar lista por si se conectó/desconectó un monitor
        self._viz_monitors = list_monitors()
        labels = [m.label for m in self._viz_monitors] or ["Monitor 1"]
        self.viz_monitor_combo["values"] = labels
        cur = self._viz_monitor_var.get()
        if cur not in labels:
            self._viz_monitor_var.set(labels[0])
        display_index = 0
        try:
            display_index = labels.index(self._viz_monitor_var.get())
        except ValueError:
            display_index = 0

        mon = (
            self._viz_monitors[display_index]
            if self._viz_monitors and 0 <= display_index < len(self._viz_monitors)
            else None
        )
        try:
            self._viz, self._viz_bus = launch_visualizer(
                on_close=_on_viz_close,
                display_index=display_index,
                monitor=mon,
            )
            mon_txt = mon.label if mon else f"Monitor {display_index + 1}"
            self.viz_btn.config(text="■  VIZ OFF", bg=NEON_ORANGE)
            self.status_label.config(text=f"[ VIZ ]  {mon_txt}  ·  ESC para cerrar")
        except Exception as exc:
            messagebox.showerror("OpenGL", str(exc))

    def _viz_closed_from_thread(self) -> None:
        self._viz = None
        self._viz_bus = None
        try:
            self.viz_btn.config(text="◈  VIZ GL", bg=NEON_BLUE)
            self.status_label.config(text="[ VIZ ]  Cerrada")
        except tk.TclError:
            pass

    def _animate_scope(self) -> None:
        scope = self.synth.get_scope_buffer()
        spectrum = self.synth.get_spectrum_buffer()
        self.scope.update_waveform(scope)
        self.spectrum.update_spectrum(spectrum)
        bus = self._viz_bus or get_viz_bus()
        if bus is not None and bus.alive:
            bus.push(scope, spectrum)
        self.root.after(40, self._animate_scope)

    def _bind_keys(self) -> None:
        # bind_all: en Windows los Scale/Combobox capturan el foco y root.bind no llega
        self.root.bind_all("<KeyPress>", self._on_key_down, add="+")
        self.root.bind_all("<KeyRelease>", self._on_key_up, add="+")
        self.root.bind("<Button-1>", lambda e: self.root.focus_set())

    def _resolve_key(self, event: tk.Event) -> Optional[str]:
        key = (event.keysym or "").lower()
        if key in self.KEY_MAP:
            return key
        char = (event.char or "").lower()
        if char in self.KEY_MAP:
            return char
        return None

    def _on_key_down(self, event: tk.Event) -> Optional[str]:
        # No interferir si el usuario escribe en un Entry
        w = event.widget
        if isinstance(w, (tk.Entry, ttk.Entry, tk.Text)):
            return None
        key = self._resolve_key(event)
        if key is None:
            return None
        # Autorepeat de Windows: ignorar KeyPress repetidos de la misma tecla
        if key in self._keys_pressed:
            return "break"
        self._keys_pressed.add(key)
        note = self.KEY_MAP[key]
        if self.engine.is_running:
            self.synth.note_on(note, 100)
        else:
            self.status_label.config(text="[!] Pulsa START AUDIO para tocar con el teclado")
        return "break"

    def _on_key_up(self, event: tk.Event) -> Optional[str]:
        w = event.widget
        if isinstance(w, (tk.Entry, ttk.Entry, tk.Text)):
            return None
        key = self._resolve_key(event)
        if key is None:
            return None
        self._keys_pressed.discard(key)
        # Si otra tecla mapea a la misma nota y sigue pulsada, no apagar
        note = self.KEY_MAP[key]
        still = any(self.KEY_MAP[k] == note for k in self._keys_pressed)
        if not still:
            self.synth.note_off(note)
        return "break"

    def _handle_close(self) -> None:
        stop_visualizer()
        self._viz = None
        self._viz_bus = None
        if self.recorder.recording:
            self.recorder.stop()
        if self.engine.is_running:
            self.engine.stop()
        self.synth.all_notes_off()
        if self.on_close:
            self.on_close()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def launch_gui(
    synth: Optional[CS80Synth] = None,
    engine: Optional[AudioEngine] = None,
    recorder: Optional[AudioRecorder] = None,
    on_close: Optional[Callable[[], None]] = None,
) -> None:
    if synth is None:
        synth = CS80Synth(SAMPLE_RATE)
    if engine is None:
        engine = AudioEngine(SAMPLE_RATE, BLOCK_SIZE, channels=2)
    if recorder is None:
        recorder = AudioRecorder(SAMPLE_RATE)
    load_preset(list_presets()[0], synth)
    CS80GUI(synth, engine, recorder, on_close=on_close).run()
