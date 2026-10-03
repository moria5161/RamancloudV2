"""Run the frozen executable from a different working directory, never Python sources."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def executable():
    if sys.platform == "darwin":
        return ROOT / "desktop/dist/RamanCloud.app/Contents/MacOS/RamanCloud"
    return ROOT / "desktop/dist/RamanCloud" / ("RamanCloud.exe" if sys.platform == "win32" else "RamanCloud")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("api", "gui"), default="api")
    args = parser.parse_args()
    binary = executable()
    if not binary.is_file():
        raise FileNotFoundError(f"Frozen application missing: {binary}")
    directory = ROOT / "desktop/test-results" / args.mode
    directory.mkdir(parents=True, exist_ok=True)
    report = directory / "smoke.json"
    report.unlink(missing_ok=True)
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    with tempfile.TemporaryDirectory(prefix="ramancloud-relocated-") as unrelated_cwd:
        result = subprocess.run([str(binary), "--gui-smoke-test" if args.mode == "gui" else "--smoke-test",
                                 "--require-frozen", "--smoke-report", str(report), "--data-dir", str(directory / "data")],
                                cwd=unrelated_cwd, env=environment, capture_output=True, text=True, timeout=300)
    (directory / "stdout.log").write_text(result.stdout, encoding="utf-8")
    (directory / "stderr.log").write_text(result.stderr, encoding="utf-8")
    print(result.stdout)
    print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"Frozen {args.mode} smoke exited {result.returncode}; diagnostics: {directory}")
    data = json.loads(report.read_text(encoding="utf-8"))
    if not all(data.get(key) is True for key in ("ok", "frozen", "shutdown")):
        raise AssertionError(f"Frozen smoke report did not pass: {data}")
    if args.mode == "api" and (len(data.get("checks", [])) < 7 or data.get("mapping_demos", 0) < 4):
        raise AssertionError("Frozen smoke skipped required integration checks")
    if args.mode == "gui" and not data.get("native", {}).get("ok"):
        raise AssertionError("Frozen native WebView smoke skipped required checks")


if __name__ == "__main__":
    main()
