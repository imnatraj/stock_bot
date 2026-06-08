#!/usr/bin/env bash
set -euo pipefail

# Run scanner CLI (ensure venv activated and PYTHONPATH includes ./src)
export PYTHONPATH=${PYTHONPATH:-}:./src
PYTHON_CMD=python
if [ -f ".venv/bin/python" ]; then
    PYTHON_CMD=".venv/bin/python"
elif ! command -v python &> /dev/null && command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
fi
$PYTHON_CMD -m stock_bot.scanner.cli
