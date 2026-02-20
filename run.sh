#!/usr/bin/env bash
# Signal Hub — run wrapper
# Activates the venv and runs the full pipeline.
# Used by cron / systemd timer.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Add nvm node bin to PATH so wrangler is found when run via systemd
export PATH="$HOME/.nvm/versions/node/v24.13.0/bin:$PATH"

# Activate virtual environment
source "$SCRIPT_DIR/venv/bin/activate"

exec python -m src.main "$@"
