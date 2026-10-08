#!/usr/bin/env bash
set -euo pipefail

mkdir -p external

clone_or_update() {
  local url="$1" dir="$2" ref="$3"
  if [[ ! -d "$dir/.git" ]]; then
    git clone --depth 1 --branch "$ref" "$url" "$dir"
  else
    git -C "$dir" fetch --depth 1 origin "$ref"
    git -C "$dir" checkout -q "$ref"
    git -C "$dir" reset --hard "origin/$ref"
  fi
}

clone_or_update "https://github.com/MatthiasJReisinger/PolyBenchC-4.2.1.git" "external/PolyBenchC" "master"
clone_or_update "https://github.com/embecosm/mibench.git" "external/MiBench" "master"
clone_or_update "https://github.com/summerspringwei/cBench.git" "external/cBench" "master"
clone_or_update "https://github.com/socal-ucr/Rodinia.git" "external/Rodinia" "master"

# LLVM Test Suite is retained as an evaluation/source inventory at this stage.
# Its native lit/CMake harness will be handled by the LLVM-suite adapter rather
# than by the generic single-program adapter.
clone_or_update "https://github.com/llvm/llvm-test-suite.git" "external/llvm-test-suite" "main"

for d in external/PolyBenchC external/MiBench external/cBench external/Rodinia external/llvm-test-suite; do
  echo "== $d =="
  git -C "$d" rev-parse HEAD
done
