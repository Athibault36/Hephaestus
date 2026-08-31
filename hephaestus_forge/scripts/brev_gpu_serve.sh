#!/usr/bin/env bash
set -euo pipefail
REPO="${1:-$HOME/Hephaestus}"
cd "$REPO/hephaestus_forge"
source .venv/bin/activate
pip install -q huggingface_hub httpx llama-cpp-python \
  --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124 2>/dev/null || \
  pip install -q huggingface_hub httpx 'llama-cpp-python[server]'
nohup python forge.py gpu-dev --repo "$REPO" --serve-only --host 0.0.0.0 --port 8080 \
  > "$HOME/gpu_dev.log" 2>&1 &
echo "GPU dev server starting — log: ~/gpu_dev.log"
