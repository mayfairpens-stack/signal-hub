#!/usr/bin/env bash
# Signal Hub — run wrapper
# Activates the venv and runs the full pipeline.
# Used by cron / systemd timer.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment
source "$SCRIPT_DIR/venv/bin/activate"

exec python -m src.main "$@"
