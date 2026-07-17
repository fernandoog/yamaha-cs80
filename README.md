# Yamaha CS-80 Simulator — Blade Runner Edition

Simulador del sintetizador **Yamaha CS-80** (~1980) con estética inspirada en *Blade Runner* (1982) y la banda sonora de Vangelis.

Escrito en **Python 3.10+**, compatible con **Linux** y **Windows**.

## Características

- Síntesis polifónica (8 voces) con doble capa, ring mod, sub-oscilador
- Filtros LP / HP / BP resonantes, envolventes ADSR dobles
- Efectos: chorus, delay, reverb, bitcrusher
- Arpegiador y secuenciador de 16 pasos con patrones Blade Runner
- GUI oscura estilo neón, osciloscopio, analizador espectral, piano virtual
- Grabación y exportación WAV, guardado de presets y sesiones
- Entrada MIDI opcional (pitch bend, mod wheel, aftertouch)
- 12 presets inspirados en Vangelis / Blade Runner

## Instalación

```bash
pip install -r requirements.txt
```

### Linux (audio + MIDI)

```bash
sudo apt install libasound2-dev portaudio19-dev
pip install -r requirements.txt
```

## Uso

```bash
python main.py                    # GUI completa
python main.py --test-poly        # Prueba de polifonía
python main.py --export-demo out.wav
python main.py --export-seq out.wav
python main.py --list-patterns
python main.py --list-devices
python main.py --midi-port "nombre del puerto"
```

### Teclado QWERTY

- **Z–M** — octava baja
- **Q–I** — octava alta

## Estructura

```
audio_engine.py    Motor de audio (sounddevice)
synth_voice.py     Voz CS-80 + polifonía + efectos
gui.py             Interfaz Blade Runner
presets.py         12 presets
step_sequencer.py  Secuenciador 16 pasos
effects.py         Delay, reverb, chorus, bitcrush
main.py            Punto de entrada
```

## Licencia

MIT
