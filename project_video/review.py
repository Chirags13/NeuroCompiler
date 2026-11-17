#!/usr/bin/env python3
"""Make a contact sheet from a rendered video: review.py <video> <out.jpg> t1 t2 ... (seconds)."""
import subprocess, sys, io
import imageio_ffmpeg
from PIL import Image
F = imageio_ffmpeg.get_ffmpeg_exe()
video, out, ts = sys.argv[1], sys.argv[2], sys.argv[3:]
w, h, cols = 640, 360, 3
S = Image.new("RGB", (w * cols + 20, (h + 10) * ((len(ts) + 2) // 3)), "white")
for i, t in enumerate(ts):
    raw = subprocess.run([F, "-v", "error", "-ss", t, "-i", video, "-frames:v", "1", "-f", "image2pipe", "-c:v", "mjpeg", "-"], capture_output=True).stdout
    S.paste(Image.open(io.BytesIO(raw)).resize((w, h)), ((i % cols) * (w + 10), (i // cols) * (h + 10)))
S.save(out, quality=85)
