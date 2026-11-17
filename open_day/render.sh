#!/usr/bin/env bash
# Build the deck and render it through Windows PowerPoint into open_day/review/.
set -e
cd "$(dirname "$0")/.."
open_day/.pptxenv/bin/python open_day/build_deck.py
W=/mnt/c/Users/Chirag/AppData/Local/Temp/nc_deck
rm -rf "$W"; mkdir -p "$W"
cp open_day/NeuroCompiler_Open_Day.pptx open_day/render.ps1 "$W/"
WP='C:\Users\Chirag\AppData\Local\Temp\nc_deck'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$WP\\render.ps1" -Src "$WP\\NeuroCompiler_Open_Day.pptx" -OutDir "$WP\\out" | tr -d '\r'
mkdir -p open_day/review
cp "$W"/out/*.png open_day/review/
cp "$W"/out/deck.pdf open_day/NeuroCompiler_Open_Day.pdf
