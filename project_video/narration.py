#!/usr/bin/env python3
"""Generate the voiceover scene by scene and record real word timings.

Each scene is spoken in one take (better intonation). `say` is what the voice reads, `show` is what the caption
prints, so "dash O three" appears as -O3. Output: public/voice/<scene>.mp3 and src/timing.json.

Usage: tools/py/bin/python narration.py
"""
import asyncio
import json
import re
import subprocess
from pathlib import Path

import edge_tts
import imageio_ffmpeg

VOICE = "en-US-AndrewNeural"
RATE = "+8%"
ROOT = Path(__file__).parent
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

SCENES = [
    ("hook", [
        ("Compile with dash O three,", "Compile with -O3,"),
        ("and one hundred nine passes run", "and 109 passes run"),
        ("in the same order, for every program.", "in the same order, for every program."),
        ("Neuro Compiler looks for a faster recipe per program,", "NeuroCompiler looks for a faster recipe per program,"),
        ("and proves it with a stopwatch.", "and proves it with a stopwatch."),
    ]),
    ("problem", [
        ("That recipe is a compromise.", "That recipe is a compromise."),
        ("One edit speeds some programs up and slows others down.", "One edit speeds some programs up and slows others down."),
        ("And the easy metric is a trap:", "And the easy metric is a trap:"),
        ("across eighteen thousand candidates,", "across 18,000 timed candidates,"),
        ("I R instruction count barely predicted speed.", "IR instruction count barely predicted speed."),
    ]),
    ("measure", [
        ("So, one rule: only measured runtime counts.", "So, one rule: only measured runtime counts."),
        ("Candidates race dash O three in shuffled rounds on a pinned core,", "Candidates race -O3 in shuffled rounds on a pinned core,"),
        ("beside an identical copy that exposes noise.", "beside an identical copy that exposes noise."),
        ("If the output changes, the candidate is rejected.", "If the output changes, the candidate is rejected."),
    ]),
    ("learn", [
        ("We searched one hundred forty six real programs,", "We searched 146 real programs,"),
        ("building over seventy thousand candidates.", "building over 70,000 candidates."),
        ("That data trains two models.", "That data trains two models."),
        ("Light G B M predicts a pipeline's speedup.", "LightGBM predicts a pipeline's speedup."),
        ("P P O, a reinforcement learning agent, invents new ones, edit by edit.", "PPO, a reinforcement learning agent, invents new ones, edit by edit."),
    ]),
    ("tune", [
        ("For a new program, P P O proposes twenty four pipelines.", "For a new program, PPO proposes 24 pipelines."),
        ("Light G B M ranks them with about nine hundred more.", "LightGBM ranks them with about 900 more."),
        ("The top eight are compiled, verified and timed.", "The top 8 are compiled, verified and timed."),
        ("The fastest must win again in a fresh run,", "The fastest must win again in a fresh run,"),
        ("or dash O three ships.", "or -O3 ships."),
        ("The models shortlist. The stopwatch decides.", "The models shortlist. The stopwatch decides."),
    ]),
    ("results", [
        ("On thirty three programs from unseen families,", "On 33 programs from unseen families,"),
        ("it averages eight percent faster than dash O three,", "it averages 8% faster than -O3,"),
        ("about five without its biggest win,", "about 5% without its biggest win,"),
        ("and none got measurably slower.", "and none got measurably slower."),
        ("On one interpreter demo, runtime fell from eight fifty milliseconds to two twenty.", "On one interpreter demo, runtime fell from 850 ms to 220."),
    ]),
    ("stack", [
        ("Built on LLVM eighteen,", "Built on LLVM 18,"),
        ("with a live dashboard showing every changed pass.", "with a live dashboard showing every changed pass."),
        ("The lesson: alone, the models are weak, and R L added little.", "The lesson: alone, the models are weak, and RL added little."),
        ("Measurement makes it reliable.", "Measurement makes it reliable."),
    ]),
    ("close", [
        ("Neuro Compiler. Faster code, measured, not guessed.", "NeuroCompiler. Faster code, measured, not guessed."),
    ]),
]


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


async def speak(sid: str, phrases) -> dict:
    text = " ".join(p[0] for p in phrases)
    com = edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary")
    audio, words = bytearray(), []
    async for ch in com.stream():
        if ch["type"] == "audio":
            audio += ch["data"]
        elif ch["type"] == "WordBoundary":
            words.append({"t": ch["offset"] / 1e7, "d": ch["duration"] / 1e7, "w": ch["text"]})
    mp3 = ROOT / "public/voice" / f"{sid}.mp3"
    mp3.parent.mkdir(parents=True, exist_ok=True)
    mp3.write_bytes(audio)
    info = subprocess.run([FFMPEG, "-i", str(mp3)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info).groups()
    dur = int(h) * 3600 + int(m) * 60 + float(s)
    # map word boundaries onto phrases by cumulative letters, so tokenization differences do not matter
    caps, i = [], 0
    for say, show in phrases:
        need, got, first = len(norm(say)), 0, None
        last = None
        while i < len(words) and got < need:
            w = words[i]
            first = first if first is not None else w["t"]
            last = w
            got += len(norm(w["w"]))
            i += 1
        caps.append({"say": say, "text": show, "start": round(first, 3), "end": round(last["t"] + last["d"], 3)})
    return {"id": sid, "duration": round(dur, 3), "phrases": caps, "words": words}


async def main():
    out = [await speak(s, p) for s, p in SCENES]
    (ROOT / "src").mkdir(exist_ok=True)
    (ROOT / "src/timing.json").write_text(json.dumps(out, indent=1))
    total = 0
    for s in out:
        print(f"{s['id']:9s} {s['duration']:6.2f}s  words {len(s['words'])}")
        total += s["duration"]
    print(f"total speech {total:.1f}s, {sum(len(s['words']) for s in out)} words")


asyncio.run(main())
