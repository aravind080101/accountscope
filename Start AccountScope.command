#!/bin/bash
# Double-click to start AccountScope. First run sets everything up (takes a minute).
cd "$(dirname "$0")" || exit 1

# Pick a Python that is 3.10 or newer.
PY=""
for p in /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 \
         /usr/local/bin/python3.12 /usr/local/bin/python3.11 python3.13 python3.12 python3.11 python3; do
  if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
    PY="$p"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10 or newer is needed. Install it with:  brew install python@3.12"
  read -r -p "Press Enter to close." _; exit 1
fi

# Fresh environment if missing or built with an old Python.
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
  echo "Setting up (first run only)..."
  rm -rf .venv
  "$PY" -m venv .venv || { read -r -p "Could not create the environment. Press Enter to close." _; exit 1; }
fi
.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt || {
  read -r -p "Installing packages failed (see above). Press Enter to close." _; exit 1; }

# Keys file.
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Add your API keys to the .env file that just opened, save it, then double-click this again."
  open -e .env
  read -r -p "Press Enter to close." _; exit 0
fi

(sleep 3 && open "http://localhost:8000") &
echo "AccountScope is running at http://localhost:8000  (close this window or press Ctrl+C to stop)"
exec .venv/bin/python -m uvicorn backend.app:app --port 8000
