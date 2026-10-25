#!/usr/bin/env bash
# One-time setup inside WSL2 Ubuntu 24.04. Run from ~/neurocompiler (NOT under /mnt/c).
set -euo pipefail

if [[ "$PWD" == /mnt/* ]]; then
  echo "Move this folder into the Linux filesystem first, e.g. cp -r . ~/neurocompiler" >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install -y clang-18 llvm-18 lld-18 build-essential valgrind python3-venv python3-pip

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo
echo "LLVM:   $(/usr/lib/llvm-18/bin/opt --version | grep -m1 'LLVM version')"
echo "Next:   source .venv/bin/activate && python -m nc.cli env"
