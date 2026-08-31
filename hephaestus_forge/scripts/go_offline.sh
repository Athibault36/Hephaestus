#!/usr/bin/env bash
# Run BEFORE powering off your PC. Work continues on Brev; instance stops when done.
set -euo pipefail
REPO="${1:-$HOME/Hephaestus}"
cd "$REPO/hephaestus_forge"
source .venv/bin/activate
pip install -q pyyaml httpx huggingface_hub "llama-cpp-python[server]" 2>/dev/null || true
CONFIG="${2:-$REPO/hephaestus_forge/forge_config/cloud_agent.yaml}"
LOG="$HOME/hephaestus_autonomous.log"
nohup python forge.py agent-run --repo "$REPO" --config "$CONFIG" > "$LOG" 2>&1 &
echo "Autonomous worker PID $!"
echo "Log: $LOG"
echo "Results: $REPO/Agent_Runtime/autonomous/"
echo "Instance will STOP when the task queue finishes (saves credits)."
