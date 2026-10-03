"""Validate offline inputs and freeze on the native target OS/architecture."""

import argparse
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from desktop.smoke import asset_manifest


def native_platform():
    machine = platform.machine().lower()
    if sys.platform == "win32" and machine in ("amd64", "x86_64"):
        return "windows-x64"
    if sys.platform == "darwin" and machine in ("x86_64", "arm64"):
        return "macos-" + ("x64" if machine == "x86_64" else "arm64")
    if sys.platform == "linux" and machine == "x86_64":
        return "linux-x64"  # Local frozen-runtime validation, not a release target.
    raise RuntimeError(f"Unsupported build host: {sys.platform}/{machine}")


def validate_inputs(frontend):
    if not (frontend / "index.html").is_file():
        raise FileNotFoundError("Missing frontend/dist/index.html. Build the existing frontend before packaging.")
    index = (frontend / "index.html").read_text(encoding="utf-8")
    if "/preprocessing/assets/" not in index:
        raise ValueError("Frontend must be built with its original /preprocessing/ base path")
    files = asset_manifest(frontend)
    if "data/world-countries.json" not in files or "data/NOTICE.txt" not in files or "logo-v1.png" not in files:
        raise ValueError("Offline globe data, its attribution, or logo is missing")
    world = json.loads((frontend / "data/world-countries.json").read_text(encoding="utf-8"))
    if len(world) < 150:
        raise ValueError("Offline globe data is incomplete")
    for asset in (ROOT / "frontend/public").rglob("*"):
        if asset.is_file():
            name = asset.relative_to(ROOT / "frontend/public").as_posix()
            if name not in files or (frontend / name).read_bytes() != asset.read_bytes():
                raise ValueError(f"Built frontend is missing or has a stale public asset: {name}")
    research = (ROOT / "frontend/src/data/research.js").read_text(encoding="utf-8")
    for image in re.findall(r"\bimage\s*:\s*['\"]([^'\"]+)['\"]", research):
        if "research/" + image not in files:
            raise ValueError(f"Research visual is not bundled locally: {image}. Ask the parent to supply it.")
    package = importlib.util.find_spec("ramancloud_backend")
    if not package or not package.submodule_search_locations:
        raise RuntimeError("Install the parent package with pip install '.[desktop]' first")
    backend = Path(next(iter(package.submodule_search_locations)))
    required = ("Bacteria.txt", "ULF.txt", "tutorial_raman.txt", "time_series_Horiba.txt", "time_series_Nanophoton.txt",
                "imaging_Horiba_Graphene.txt", "imaging_Nanophoton_Hela.txt")
    for name in required:
        if not (backend / "samples" / name).is_file():
            raise FileNotFoundError(f"Parent Python package is missing samples/{name}")
    if not (backend / "historical_visits.json").is_file():
        raise FileNotFoundError("Parent package is missing historical_visits.json")
    return {"files": files, "version": importlib.metadata.version("ramancloud")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("windows-x64", "macos-x64", "macos-arm64", "linux-x64"))
    args = parser.parse_args()
    host = native_platform()
    if args.platform and args.platform != host:
        parser.error(f"Build {args.platform} on its native runner, not {host}")
    frontend = ROOT / "frontend/dist"
    manifest = validate_inputs(frontend)
    directory = ROOT / "desktop/build"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "desktop-assets.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    environment = dict(os.environ, RAMANCLOUD_BUILD_PLATFORM=host)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--workpath", str(directory), "--distpath", str(ROOT / "desktop/dist"),
                    str(ROOT / "desktop/ramancloud.spec")], cwd=ROOT, env=environment, check=True)


if __name__ == "__main__":
    main()
