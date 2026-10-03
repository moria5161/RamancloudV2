"""Black-box checks against the real socket, backend package, and bundled assets."""

import hashlib
import io
import json
import math
import sys
import uuid
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request

from .runtime import UI_ROUTES, local_opener


def ensure(condition, message):
    if not condition:
        raise AssertionError(message)


def asset_manifest(frontend):
    return {path.relative_to(frontend).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(frontend.rglob("*")) if path.is_file()}


class Client:
    def __init__(self, origin):
        self.origin = origin
        self.opener = local_opener()

    def request(self, path, data=None, headers=None, method=None, expected=200):
        request = Request(self.origin + path, data=data, headers=headers or {}, method=method)
        try:
            response = self.opener.open(request, timeout=90)
        except HTTPError as error:
            response = error
        with response:
            body = response.read()
            ensure(response.status == expected, f"{path}: expected HTTP {expected}, got {response.status}: {body[:500]!r}")
            return body, response.headers

    def json(self, path, payload=None, method=None, headers=None, expected=200):
        combined = {"Content-Type": "application/json", **(headers or {})}
        data = None if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
        body, _ = self.request(path, data, combined, method, expected)
        return json.loads(body)

    def api(self, endpoint, payload=None, method=None):
        result = self.json("/preprocessing/api/" + endpoint, payload, method)
        ensure(result.get("code") == 0, f"API failed: {endpoint}: {result}")
        return result["data"]

    def multipart(self, endpoint, fields=(), files=()):
        boundary = "ramancloud-" + uuid.uuid4().hex
        chunks = []
        for name, value in fields:
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        for name, filename, content in files:
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\nContent-Type: text/plain\r\n\r\n'.encode())
            chunks.extend((content, b"\r\n"))
        chunks.append(f"--{boundary}--\r\n".encode())
        return self.request("/preprocessing/api/" + endpoint, b"".join(chunks),
                            {"Content-Type": "multipart/form-data; boundary=" + boundary})[0]


def run_smoke_test(runtime, frontend):
    client = Client(runtime.origin)
    checks = []
    health = client.api("health")
    ensure(client.json("/api/health")["data"] == health, "Original /api routes changed")
    checks.append("original-and-prefixed-health")
    for path in ("/preprocessing/openapi.json", "/openapi.json"):
        schema = client.json(path)
        ensure("/api/process" in schema["paths"], "API schema was swallowed by static routing")
    for path in ("/preprocessing/docs", "/preprocessing/redoc"):
        body, _ = client.request(path)
        ensure(b"/preprocessing/openapi.json" in body, "Mounted API documentation has the wrong schema URL")
    for path in ("/preprocessing/api/not-a-route", "/preprocessing/assets/missing.js", "/preprocessing/research/missing.png"):
        body, _ = client.request(path, expected=404)
        ensure(b'<div id="root"' not in body, "Missing API/assets returned the SPA index")
    client.request("/preprocessing/api/health", headers={"Origin": "https://untrusted.invalid"}, expected=403)
    client.request("/preprocessing/api/health", headers={"Host": "untrusted.invalid"}, expected=403)
    checks.append("docs-routing-and-local-origin-guards")

    for route in UI_ROUTES:
        body, headers = client.request("/preprocessing/" + route)
        ensure(b'<div id="root"' in body and b"__desktop__/bridge.js" in body, f"Missing UI route: {route}")
        ensure("connect-src 'self' blob:" in headers.get("Content-Security-Policy", ""), "Offline content policy missing")
    bridge, _ = client.request("/preprocessing/__desktop__/bridge.js")
    ensure(b"begin_download" in bridge, "Native download bridge is not served")
    manifest_path = Path(sys._MEIPASS) / "desktop-assets.json" if getattr(sys, "frozen", False) else None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path else {"files": asset_manifest(frontend)}
    files = manifest["files"]
    ensure(files == asset_manifest(frontend), "Frozen frontend differs from the build manifest")
    ensure("data/world-countries.json" in files and "logo-v1.png" in files, "Offline globe/logo missing")
    ensure(any(path.startswith("research/") for path in files), "Offline research visuals missing")
    for path, digest in files.items():
        if path == "index.html":
            continue  # The shell adds its bridge script to this one response.
        body, headers = client.request("/preprocessing/" + quote(path))
        ensure(hashlib.sha256(body).hexdigest() == digest, f"Static asset damaged or shadowed: {path}")
        if path.endswith(".js"):
            ensure("javascript" in headers.get("Content-Type", ""), "JS received the wrong MIME type")
    world = client.json("/preprocessing/data/world-countries.json")
    ensure(isinstance(world, list) and len(world) >= 150 and all("polygons" in item for item in world), "Globe data is invalid")
    checks.append("all-ui-routes-and-all-static-asset-hashes")

    demos = {name: client.api("demo/" + name) for name in health["spectra_demos"]}
    ensure(set(demos) >= {"bacteria", "ulf", "tutorial"}, "Spectral demo samples missing")
    spectrum = demos["tutorial"]
    ensure(len(spectrum["wavenumber"]) == len(spectrum["intensity"]) >= 256, "Demo spectrum is truncated")
    payload = {key: spectrum[key][:256] for key in ("wavenumber", "intensity")}
    for method in health["denoise"]:
        if method == "tsvd":
            continue
        result = client.api("process", dict(payload, steps=[{"type": "denoise", "method": method}]))
        ensure(len(result["intensity"]) == 256 and all(math.isfinite(x) for x in result["intensity"]), "Denoise failed: " + method)
    for method in health["baseline"]:
        result = client.api("process", dict(payload, steps=[{"type": "baseline", "method": method}]))
        ensure(len(result["intensity"]) == 256 and all(math.isfinite(x) for x in result["intensity"]), "Baseline failed: " + method)
    steps = [{"type": "cut", "params": {"start": min(payload["wavenumber"]), "end": max(payload["wavenumber"])}},
             {"type": "denoise", "method": "sg"}, {"type": "baseline", "method": "imodpoly"}]
    processed = client.api("process", dict(payload, steps=steps))
    ensure(len(processed["history"]) == 3 and processed["baseline"] is not None, "Full processing pipeline failed")
    batch = client.api("process-batch", {"spectra": [dict(payload, filename=f"smoke-{i}.txt") for i in range(3)],
                                         "steps": [{"type": "denoise", "method": "tsvd"}]})
    ensure(len(batch["spectra"]) == 3, "TSVD batch processing failed")
    downloaded, headers = client.request("/preprocessing/api/download", json.dumps(dict(payload, filename="smoke.txt")).encode(),
                                         {"Content-Type": "application/json"})
    ensure(b"\t" in downloaded and "attachment" in headers.get("Content-Disposition", ""), "Spectrum export failed")
    uploaded = json.loads(client.multipart("upload", files=[("files", "smoke.txt", downloaded)]))
    ensure(uploaded["code"] == 0 and len(uploaded["data"]["spectra"][0]["intensity"]) == 256, "Spectrum upload roundtrip failed")
    checks.append("all-spectral-demos-algorithms-batch-upload-and-export")

    dataset_ids = []
    for name in health["mapping_demos"]:
        mapping = client.api("demo-hyperspectral/" + name)
        dataset_ids.append(mapping["dataset_id"])
        ensure(mapping["shape"][-1] == len(mapping["wavenumber"]), "Mapping demo has inconsistent dimensions")
        # Exercise every full demo's data cache without expensive full-cube baseline fits.
        result = client.api("process-hyperspectral", {"dataset_id": mapping["dataset_id"], "wavenumber": mapping["wavenumber"],
                                                     "steps": [{"type": "denoise", "method": "sg"}]})
        dataset_ids.append(result["processed_dataset_id"])
        ensure(result["shape"] == mapping["shape"], "Processing changed the mapping dimensions")
        preview = client.api("hyperspectral-slice/" + result["processed_dataset_id"])
        ensure(preview["preview"], "Mapping heatmap is empty")
        endpoint = "hyperspectral-pixel/" if mapping["mode"] == "imaging" else "hyperspectral-spectrum/"
        pixel = client.api(endpoint + result["processed_dataset_id"])
        ensure(len(pixel["intensity"]) == len(result["wavenumber"]), "Mapping spectrum readback failed")
    for dataset_id in dataset_ids:
        released = client.json("/preprocessing/api/datasets/" + dataset_id, method="DELETE")
        ensure(released["code"] == 0, "Mapping dataset cleanup failed")
    checks.append("all-imaging-and-time-series-demos-process-slice-spectrum-and-release")

    horiba = b"\t\t100\t200\t300\n0\t0\t1\t2\t3\n0\t1\t4\t5\t6\n"
    split = client.multipart("tools/split", fields=[("instrument", "Horiba")], files=[("file", "mapping.txt", horiba)])
    with zipfile.ZipFile(io.BytesIO(split)) as archive:
        ensure(len(archive.namelist()) == 2 and archive.testzip() is None, "Split ZIP is invalid")
    merged = client.multipart("tools/merge", files=[("files", "one.txt", b"100\t1\n200\t2\n300\t3\n"),
                                                    ("files", "two.txt", b"100\t4\n200\t5\n300\t6\n")])
    ensure(b"\t" in merged and len(merged.splitlines()) >= 3, "Merge tool failed")
    converted = client.multipart("tools/convert", fields=[("conversion", "horiba_to_nanophoton")], files=[("file", "mapping.txt", horiba)])
    restored = client.multipart("tools/convert", fields=[("conversion", "nanophoton_to_horiba")], files=[("file", "mapping.txt", converted)])
    loaded = json.loads(client.multipart("upload-hyperspectral", fields=[("instrument", "Horiba"), ("mode", "imaging")],
                                         files=[("file", "restored.txt", restored)]))
    ensure(loaded["code"] == 0 and loaded["data"]["shape"][-1] == 3, "Conversion/upload roundtrip failed")
    client.json("/preprocessing/api/datasets/" + loaded["data"]["dataset_id"], method="DELETE")
    checks.append("split-zip-merge-and-bidirectional-format-conversion")

    summary = client.json("/preprocessing/api/visits/summary")
    ensure("countries" in summary, "Offline statistics/history missing")
    event = {"event_id": str(uuid.uuid4()), "session_id": str(uuid.uuid4()), "path": "/spectral"}
    recorded = client.json("/preprocessing/api/visits/pageview", event, headers={"Origin": runtime.origin})
    ensure(recorded["recorded"], "Local pageview could not be persisted")
    checks.append("offline-analytics-history-and-writable-storage")
    return {"checks": checks, "asset_count": len(files), "spectral_demos": len(demos), "mapping_demos": len(health["mapping_demos"])}
