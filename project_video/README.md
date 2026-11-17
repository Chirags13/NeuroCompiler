# NeuroCompiler explainer video

`final_video.mp4` is 1920x1080, 30 fps, 1:43, with burned-in captions. `captions.srt` holds the same captions as a separate file.

| File | Purpose |
|---|---|
| `final_video.mp4` | the finished video |
| `script.md`, `storyboard.md`, `captions.srt` | narration, scene breakdown with sources, subtitles (written by `mix.py`) |
| `narration.py` | the script text; generates the voice and real word timings (`src/timing.json`) |
| `export_data.py` | exports real project numbers to `src/data.json` |
| `mix.py` | timeline, synthesized music and effects, mix, captions, documents |
| `src/` | Remotion scenes (React) |
| `build.sh` | full build; `check_speech.py` and `review.py` are the review tools |

## Rebuild

`tools/` and `node_modules/` are not kept in git. To recreate them, in this folder:

```bash
# Node 22 in tools/node, Python tools in tools/py
curl -fsSL https://nodejs.org/dist/v22.11.0/node-v22.11.0-linux-x64.tar.xz | tar xJ -C tools && ln -sfn node-v22.11.0-linux-x64 tools/node
../.venv/bin/python -m venv tools/py && tools/py/bin/pip install edge-tts numpy scipy imageio-ffmpeg pillow faster-whisper
PATH=$PWD/tools/node/bin:$PATH npm install
```

`tools/env.sh` sets `PATH`, `LD_LIBRARY_PATH` and `F` (the ffmpeg path). The render browser needs `libasound.so.2`: install `libasound2t64`, or unpack it into `tools/libs` as was done here.

```bash
tools/py/bin/python narration.py   # only if the words change
./build.sh
```

## Notes

- Voice: Microsoft `en-US-AndrewNeural` through `edge-tts`, an online service with no key. Check Microsoft's terms before any commercial use.
- Music and sound effects are synthesized in `mix.py`, so there is no third-party music licence.
- Fonts: Inter and JetBrains Mono (SIL Open Font License), the same files the dashboard uses.
- Remotion is free for individuals and small teams; see remotion.dev/license.
