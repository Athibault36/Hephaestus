#!/usr/bin/env bash
# HephaestusForge Cloud Agent bootstrap.
# Idempotent: safe to re-run against cached or partially prepared state.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# --- Python: HephaestusForge CLI + agent runtime -----------------------------
# Debian/Ubuntu split the venv/ensurepip bootstrap into a separate package.
if ! python3 -m venv --help >/dev/null 2>&1 \
   || ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y --no-install-recommends python3-venv
fi

if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r hephaestus_forge/requirements.txt

# --- Frontend: Mission Control dashboard (React + Vite) ----------------------
(
  cd hephaestus_forge/templates/mission_control
  npm install
)

echo "HephaestusForge environment ready."
echo "  CLI:       source .venv/bin/activate && python -m hephaestus_forge.forge --help"
echo "  Dashboard: cd hephaestus_forge/templates/mission_control && npm run dev"
