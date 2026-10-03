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
    parser.add_argument("--allow-webgl-fallback", action="store_true")
    args = parser.parse_args()
    if args.allow_webgl_fallback and args.mode != "gui":
        parser.error("--allow-webgl-fallback requires --mode gui")
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
        command = [str(binary), "--gui-smoke-test" if args.mode == "gui" else "--smoke-test",
                   "--require-frozen", "--smoke-report", str(report), "--data-dir", str(directory / "data")]
        if args.allow_webgl_fallback:
            command.append("--allow-webgl-fallback")
        result = subprocess.run(command,
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
    if args.mode == "gui":
        native = data["native"]
        if not native.get("spectral_svg") or not native.get("bridge"):
            raise AssertionError("Native SVG processing or export checks did not pass")
        if not (native.get("webgl2") and native.get("globe")):
            diagnostics = native.get("webgl_diagnostics", {})
            if not (args.allow_webgl_fallback and native.get("globe_fallback") and native.get("regions", 0) >= 20
                    and diagnostics.get("lost") is True and diagnostics.get("error") == 37442):
                raise AssertionError("Native globe did not render or verify the documented context-loss fallback")


if __name__ == "__main__":
    main()
