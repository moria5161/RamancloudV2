#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
python_bin="${RAMANCLOUD_BUILD_PYTHON:-python3.11}"
"$python_bin" -c 'import sys; assert sys.version_info[:2] == (3, 11), "Build alpha with Python 3.11"'
node -e 'if (Number(process.versions.node.split(".")[0]) < 24) throw new Error("Build alpha with Node.js 24 or later")'

"$python_bin" -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m pip check
"$python_bin" scripts/setup_ssnet.py
.venv-vib2mol/bin/python -m pip check
(
    cd frontend
    npm ci --no-audit --no-fund
    RAMANCLOUD_BASE_PATH=/alpha/ npm run build
)
test -s frontend/dist/index.html
