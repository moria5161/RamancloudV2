"""Archive native bundles and validate release asset checksums without dependencies."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def archive(platform):
    for mode in ("api", "gui", "ui"):
        filename = "result.json" if mode == "ui" else "smoke.json"
        report = json.loads((ROOT / "desktop/test-results" / mode / filename).read_text(encoding="utf-8"))
        if not all(report.get(key) is True for key in ("ok", "frozen", "shutdown")):
            raise ValueError(f"Cannot archive a bundle without a passing frozen {mode} test")
    manifest = json.loads((ROOT / "desktop/build/desktop-assets.json").read_text(encoding="utf-8"))
    directory = ROOT / "desktop/artifacts"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"RamanCloud-{manifest['version']}-{platform}.zip"
    if platform.startswith("macos-"):
        if sys.platform != "darwin":
            raise RuntimeError("macOS app archives must be created on macOS")
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                        str(ROOT / "desktop/dist/RamanCloud.app"), str(target)], check=True)
    else:
        shutil.make_archive(str(target.with_suffix("")), "zip", root_dir=ROOT / "desktop/dist", base_dir="RamanCloud")
    target.with_name(target.name + ".sha256").write_text(f"{digest(target)}  {target.name}\n", encoding="ascii")
    print(target)


def checksums(directory):
    for checksum in directory.glob("*.sha256"):
        for line in checksum.read_text(encoding="ascii").splitlines():
            expected, name = line.split("  ", 1)
            if Path(name).name != name or not (directory / name).is_file() or digest(directory / name) != expected:
                raise ValueError(f"Release asset checksum mismatch: {checksum}")
    assets = sorted(path for path in directory.iterdir() if path.is_file() and path.name != "SHA256SUMS.txt" and path.suffix != ".sha256")
    if not assets:
        raise ValueError("No release assets to publish")
    (directory / "SHA256SUMS.txt").write_text("".join(f"{digest(path)}  {path.name}\n" for path in assets), encoding="ascii")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    bundle = commands.add_parser("archive")
    bundle.add_argument("--platform", choices=("windows-x64", "macos-x64", "macos-arm64"), required=True)
    manifest = commands.add_parser("checksums")
    manifest.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "archive":
        archive(args.platform)
    else:
        checksums(args.directory)


if __name__ == "__main__":
    main()
