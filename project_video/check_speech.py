#!/usr/bin/env python3
"""Transcribe the final audio and compare with the script, to catch words lost under the music."""
import difflib, json, re, subprocess
import imageio_ffmpeg, numpy as np
from faster_whisper import WhisperModel
m = WhisperModel("base.en", device="cpu", compute_type="int8")
raw = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", "final_video.mp4", "-f", "f32le", "-ac", "1", "-ar", "16000", "-"], capture_output=True).stdout
segs, _ = m.transcribe(np.frombuffer(raw, dtype=np.float32), beam_size=5)
text = " ".join(s.text.strip() for s in segs)
print(text)
tl = json.load(open("src/timeline.json"))
ref = " ".join(p["say"] for s in tl["scenes"] for p in s["phrases"])
n = lambda s: re.sub(r"[^a-z0-9 ]", "", s.lower()).split()
print("\nword match ratio:", round(difflib.SequenceMatcher(None, n(ref), n(text)).ratio(), 3))
