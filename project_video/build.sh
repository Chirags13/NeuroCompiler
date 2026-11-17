#!/usr/bin/env bash
# Full build: voice timings -> mix and documents -> video render -> loudness-normalized mux into final_video.mp4
# Needs tools/ (see README.md). Regenerate the voice first with: tools/py/bin/python narration.py
set -e
cd "$(dirname "$0")"; . tools/env.sh
tools/py/bin/python mix.py
npx remotion render src/index.ts Explainer out/video.mp4 --concurrency=8 --crf=17 --color-space=bt709 --pixel-format=yuv420p --muted --log=error | tail -1
$F -v error -y -i public/mix.wav -af loudnorm=I=-16:TP=-1.5:LRA=11 -ar 48000 -c:a pcm_s16le out/mix_norm.wav
$F -v error -y -i out/video.mp4 -i out/mix_norm.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -movflags +faststart -shortest final_video.mp4
ls -la final_video.mp4
