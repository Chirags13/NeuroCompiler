#!/usr/bin/env python3
"""Lay out the timeline from the real voice timings, synthesize the music and sound effects, mix everything,
and write public/mix.wav, src/timeline.json, captions.srt, script.md and storyboard.md.

All music and effects are generated here, so the soundtrack has no third-party licence.
Usage: tools/py/bin/python mix.py
"""
import json
import subprocess
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, fftconvolve, sosfilt

ROOT = Path(__file__).parent
SR, FPS = 44100, 30
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
LEAD, GAP, TAIL = 0.5, 0.42, 2.4
rng = np.random.default_rng(7)

timing = json.loads((ROOT / "src/timing.json").read_text())

# ---------------------------------------------------------------- timeline
scenes, t = [], LEAD
for i, s in enumerate(timing):
    start = 0.0 if i == 0 else t - 0.2
    voice = t
    dur = s["duration"] + GAP + (TAIL if s["id"] == "close" else 0)
    end = t + dur
    scenes.append({"id": s["id"], "start": round(start, 3), "dur": round(end - start, 3), "voice": round(voice, 3),
                   "phrases": [{"text": p["text"], "say": p["say"], "start": round(voice + p["start"], 3), "end": round(voice + p["end"], 3)} for p in s["phrases"]]})
    t = end
total = round(t, 3)
(ROOT / "src/timeline.json").write_text(json.dumps({"fps": FPS, "total": total, "scenes": scenes}, indent=1))


# ---------------------------------------------------------------- voice
def load(path):
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(float)


n = int(total * SR) + SR
voice = np.zeros(n)
for s in scenes:
    v = load(ROOT / "public/voice" / f"{s['id']}.mp3")
    a = int(s["voice"] * SR)
    voice[a:a + len(v)] += v[:len(voice) - a]
voice *= 0.80 / np.max(np.abs(voice))


# ---------------------------------------------------------------- music
def lp(x, fc, order=2):
    return sosfilt(butter(order, fc / (SR / 2), "low", output="sos"), x)


def hp(x, fc, order=2):
    return sosfilt(butter(order, fc / (SR / 2), "high", output="sos"), x)


BPM = 96
beat = 60 / BPM
bar = 4 * beat
tt = np.arange(n) / SR
# Am  F  C  G, as root + chord tones (Hz)
A3, F3, C4, G3 = 220.0, 174.61, 261.63, 196.0
CHORDS = [(A3, [1, 1.1892, 1.4983]), (F3, [1, 1.2599, 1.4983]), (C4 / 2, [1, 1.2599, 1.4983]), (G3, [1, 1.2599, 1.4983])]
pad, pluck, sub = np.zeros(n), np.zeros(n), np.zeros(n)
for b in range(int(total / bar) + 2):
    root, tones = CHORDS[b % 4]
    a, m = int(b * bar * SR), int(bar * 1.15 * SR)
    if a >= n:
        break
    seg = np.arange(min(m, n - a)) / SR
    env = np.minimum(1, seg / 0.9) * np.minimum(1, (seg[-1] - seg + 1e-3) / 0.9)
    tone = sum(np.sin(2 * np.pi * root * r * d * seg + rng.random() * 6) for r in tones for d in (0.997, 1.003, 2.0))
    pad[a:a + len(seg)] += tone * env
    sl = np.arange(min(int(bar * SR), n - a)) / SR
    sub[a:a + len(sl)] += np.sin(2 * np.pi * root / 2 * sl) * np.minimum(1, sl / 0.03) * np.exp(-sl * 1.6)
    # arpeggio on eighth notes
    pattern = [0, 1, 2, 3, 2, 1, 3, 2]
    for k, p in enumerate(pattern):
        o = a + int(k * beat / 2 * SR)
        if o >= n:
            break
        f0 = root * 2 * (tones + [2.0])[p]
        sg = np.arange(min(int(0.7 * SR), n - o)) / SR
        pluck[o:o + len(sg)] += (np.sin(2 * np.pi * f0 * sg) + 0.3 * np.sin(4 * np.pi * f0 * sg)) * np.exp(-sg * 7) * (0.7 + 0.3 * rng.random())
pad = lp(pad, 900) / 9
pluck = lp(pluck, 3500) * 0.12
sub = sub * 0.28
# soft hi-hat pulse from the "measure" scene on: the sound of a clock
hat = np.zeros(n)
for k in range(int(total / (beat / 2))):
    o = int(k * beat / 2 * SR)
    sg = int(0.05 * SR)
    if o + sg < n:
        hat[o:o + sg] += hp(rng.normal(size=sg), 7000) * np.exp(-np.arange(sg) / (0.012 * SR)) * (1.0 if k % 2 else 0.55)
hat *= 0.05


def curve(points):
    xs, ys = zip(*points)
    return np.interp(tt, xs, ys)


S = {s["id"]: s for s in scenes}
pad_e = curve([(0, 0), (2, .8), (S["measure"]["start"], .8), (S["tune"]["start"], 1), (S["results"]["start"], 1.1), (S["close"]["start"], 1.1), (total - 1.8, .7), (total, 0)])
pluck_e = curve([(0, 0), (S["problem"]["start"], .35), (S["measure"]["start"], .7), (S["tune"]["start"], 1), (S["stack"]["start"], .8), (total - 2.5, .6), (total, 0)])
sub_e = curve([(0, 0), (S["measure"]["start"], .0), (S["measure"]["start"] + 1, .7), (S["results"]["start"], 1), (total - 2, .5), (total, 0)])
hat_e = curve([(0, 0), (S["measure"]["start"], 0), (S["measure"]["start"] + .5, 1), (S["stack"]["start"], 1), (S["stack"]["start"] + 3, .4), (S["close"]["start"], 0), (total, 0)])
music = pad * pad_e + pluck * pluck_e + sub * sub_e + hat * hat_e
ir = rng.normal(size=int(1.6 * SR)) * np.exp(-np.arange(int(1.6 * SR)) / (0.42 * SR))
music = music + 0.12 * fftconvolve(music, ir, mode="full")[:n] / np.sqrt(len(ir))


# ---------------------------------------------------------------- sound effects
def place(buf, at, x, gain=1.0):
    a = int(at * SR)
    m = min(len(x), len(buf) - a)
    if m > 0 and a >= 0:
        buf[a:a + m] += x[:m] * gain


def whoosh(d=0.55):
    m = int(d * SR)
    x = rng.normal(size=m)
    out, step = np.zeros(m), 512
    for i in range(0, m, step):
        fc = 300 + 3200 * np.sin(np.pi * i / m) ** 2
        out[i:i + step] = lp(x[i:i + step], fc, 1)
    return out * np.sin(np.pi * np.arange(m) / m) ** 2


def ding(f0=880.0, d=1.0):
    s_ = np.arange(int(d * SR)) / SR
    return (np.sin(2 * np.pi * f0 * s_) + .4 * np.sin(2 * np.pi * f0 * 2.01 * s_) + .2 * np.sin(2 * np.pi * f0 * 3 * s_)) * np.exp(-s_ * 5)


def thud():
    s_ = np.arange(int(.5 * SR)) / SR
    return np.sin(2 * np.pi * (70 - 25 * s_) * s_) * np.exp(-s_ * 7)


def tick():
    s_ = np.arange(int(.03 * SR)) / SR
    return np.sin(2 * np.pi * 2100 * s_) * np.exp(-s_ * 180)


sfx = np.zeros(n)
for s in scenes[1:]:
    place(sfx, s["start"] - 0.1, whoosh(), 0.20)


def ph(sc, i):
    return S[sc]["phrases"][i]["start"]


place(sfx, ph("hook", 3) - 0.05, thud(), 0.5)            # title reveal
place(sfx, ph("hook", 3) - 0.05, ding(660, 1.6), 0.10)
for k in range(10):                                      # interleaved rounds filling up
    place(sfx, ph("measure", 1) + k * 0.33, tick(), 0.16)
place(sfx, ph("measure", 3) + 0.34, ding(990, .6), 0.10)  # keep
place(sfx, ph("measure", 3) + 1.15, ding(196, .6), 0.14)  # rejected
for k in range(8):                                       # top-8 timing
    place(sfx, ph("tune", 2) + 0.6 + k * 0.16, tick(), 0.13)
place(sfx, ph("tune", 5) - 0.1, ding(880, 1.2), 0.11)
place(sfx, ph("results", 1), thud(), 0.45)
place(sfx, ph("results", 1), ding(1046.5, 1.2), 0.09)
place(sfx, ph("close", 0) - 0.05, thud(), 0.45)
place(sfx, ph("close", 0) - 0.05, ding(660, 2.0), 0.10)

# ---------------------------------------------------------------- ducking and master
env = np.abs(voice)
win = int(0.12 * SR)
env = np.convolve(env, np.ones(win) / win, mode="same")
speaking = np.clip(env / (0.35 * env.max()), 0, 1)
kernel = np.hanning(int(0.5 * SR)); kernel /= kernel.sum()
speaking = np.clip(np.convolve(speaking, kernel, mode="same") * 2.2, 0, 1)
duck = 1 - 0.62 * speaking
music *= 0.056 / (np.sqrt(np.mean(music ** 2)) + 1e-9)

L = voice + music * duck * 1.03 + sfx * 0.9
R = voice + np.roll(music, 90) * duck * 0.97 + sfx * 1.0
m = max(np.max(np.abs(L)), np.max(np.abs(R)))
gain = min(1.0, 0.95 / m)
stereo = np.stack([L, R], axis=1)[: int(total * SR)] * gain
fade = int(.8 * SR)
stereo[-fade:] *= np.linspace(1, 0, fade)[:, None]
wavfile.write(ROOT / "public/mix.wav", SR, (stereo * 32767).astype(np.int16))
rv = 20 * np.log10(np.sqrt(np.mean(voice[voice != 0] ** 2)))
rm = 20 * np.log10(np.sqrt(np.mean((music * duck) ** 2)))
print(f"total {total:.2f}s  peak gain {gain:.2f}  voice RMS {rv:.1f} dB  ducked music RMS {rm:.1f} dB")


# ---------------------------------------------------------------- captions and documents
def stamp(x):
    ms = int(round(x * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def mmss(x):
    return f"{int(x) // 60}:{int(x) % 60:02d}"


srt, i = [], 1
for s in scenes:
    for p in s["phrases"]:
        srt.append(f"{i}\n{stamp(p['start'])} --> {stamp(p['end'] + 0.1)}\n{p['text']}\n")
        i += 1
(ROOT / "captions.srt").write_text("\n".join(srt))

TITLES = {"hook": "Introduction", "problem": "Problem", "measure": "Measurement", "learn": "Data and models", "tune": "How tune mode works",
          "results": "Results", "stack": "Implementation and honest lesson", "close": "Close"}
script = ["# NeuroCompiler explainer: narration script", "",
          f"Voice: `en-US-AndrewNeural` (Microsoft neural voice via edge-tts). Length {mmss(total)}. Lines are as captioned; the voice reads numbers and acronyms spelled out (see `narration.py`).", ""]
for s in scenes:
    script += [f"## {mmss(s['start'])} {TITLES[s['id']]}", ""] + [p["text"] for p in s["phrases"]] + [""]
(ROOT / "script.md").write_text("\n".join(x if x.startswith("#") or x == "" or x.startswith("Voice") else x + "  " for x in script))

BOARD = json.loads((ROOT / "storyboard_notes.json").read_text())
board = ["# NeuroCompiler explainer: storyboard", "", "Timestamps come from the real voice timings (`mix.py`). Every number is from a result file in this repo; sources are listed per scene.", ""]
for s in scenes:
    b = BOARD[s["id"]]
    board += [f"## {mmss(s['start'])}–{mmss(s['start'] + s['dur'])} · {TITLES[s['id']]}", "", f"**Visual:** {b['visual']}", "", f"**Sound:** {b['sound']}", "", f"**Source of the numbers:** {b['source']}", ""]
(ROOT / "storyboard.md").write_text("\n".join(board))
