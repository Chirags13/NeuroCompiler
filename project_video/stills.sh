#!/usr/bin/env bash
# Render review stills: ./stills.sh 12.5 40 ...  (times in seconds) -> out/stills/
mkdir -p out/stills
for t in "$@"; do f=$(python3 -c "print(int($t*30))"); npx remotion still src/index.ts Explainer out/stills/f$(printf %05d $f).jpg --frame=$f --image-format=jpeg --log=error; done
