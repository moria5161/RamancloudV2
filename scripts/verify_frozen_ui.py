"""Exercise the complete UI served by the actual relocated native executable."""

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path)
    args = parser.parse_args()
    if args.executable:
        binary = args.executable.resolve()
    elif sys.platform == "darwin":
        binary = ROOT / "desktop/dist/RamanCloud.app/Contents/MacOS/RamanCloud"
    else:
        binary = ROOT / "desktop/dist/RamanCloud" / ("RamanCloud.exe" if os.name == "nt" else "RamanCloud")
    if not binary.is_file():
        raise FileNotFoundError(binary)
    output = ROOT / "desktop/test-results/ui"
    output.mkdir(parents=True, exist_ok=True)
    ready = output / "ready.json"
    ready.unlink(missing_ok=True)
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["RAMANCLOUD_TEST_OUTPUT"] = str(output)
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    with tempfile.TemporaryDirectory(prefix="ramancloud-ui-relocated-") as unrelated_cwd:
        with (output / "server.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen([str(binary), "--serve", "--require-frozen", "--native-downloads",
                                       "--ready-file", str(ready), "--data-dir", str(output / "data")],
                                      cwd=unrelated_cwd, env=environment, stdout=log, stderr=log,
                                      creationflags=flags)
            try:
                deadline = time.monotonic() + 90
                while not ready.is_file():
                    if server.poll() is not None:
                        raise RuntimeError(f"Frozen server exited {server.returncode}; see {log.name}")
                    if time.monotonic() > deadline:
                        raise TimeoutError("Frozen server did not become ready")
                    time.sleep(0.1)
                info = json.loads(ready.read_text(encoding="utf-8"))
                if info.get("frozen") is not True or info.get("pid") != server.pid:
                    raise AssertionError("UI check must use the frozen process it launched")
                environment["RAMANCLOUD_TEST_URL"] = info["url"]
                subprocess.run(["node", str(ROOT / "scripts/verify_desktop_ui.cjs")], env=environment,
                               cwd=ROOT, check=True, timeout=420)
            finally:
                if server.poll() is None:
                    server.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM)
                    try:
                        server.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=10)
                        raise RuntimeError("Frozen server required forced termination")
                if server.returncode != 0:
                    raise RuntimeError(f"Frozen server did not shut down cleanly: {server.returncode}")
    if ready.exists():
        raise AssertionError("Frozen process left a stale readiness file")
    (output / "result.json").write_text(json.dumps({"ok": True, "frozen": True, "shutdown": True}) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
