#!/usr/bin/env python3
"""Verify an installed RamanCloud wheel, not the checkout or an editable install.

Run with the Python interpreter from the fresh venv that contains the wheel:
  /tmp/check/bin/python scripts/verify_mcp_package.py \
      --executable /tmp/check/bin/ramancloud-mcp --output-dir /tmp/mcp-evidence

The output directory must be empty or absent. Only the executable is launched;
the server's working directory is a separate temporary directory. Evidence,
including verification.json and server.stderr.log, is retained on failure.
"""

import argparse
import asyncio
import csv
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import math
import os
import sys
import tempfile
import zipfile
from datetime import timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


TOOL_NAMES = {
    "inspect_capabilities", "inspect_file", "load_demo", "process_spectrum",
    "process_batch", "process_time_series", "process_imaging", "split_mapping",
    "merge_spectra", "convert_mapping",
}
MAX_RESPONSE_BYTES = 16 * 1024


class VerificationError(RuntimeError):
    pass


def write_new(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sniff_format(path: Path) -> str:
    if zipfile.is_zipfile(path):
        return "zip"
    with path.open("rb") as stream:
        prefix = stream.read(256).lstrip()
    if prefix.startswith((b"<?xml", b"<svg")):
        return "svg"
    if prefix.startswith((b"{", b"[")):
        return "json"
    if b"\t" in prefix and b"\x00" not in prefix:
        return "tsv"
    return "unknown"


def check_bounded(value: Any, key: str = "result") -> None:
    if isinstance(value, dict):
        for child_key, child in value.items():
            if child_key in ("wavenumber", "intensity", "spectra", "mean_spectrum", "baseline", "preview") and isinstance(child, list):
                raise VerificationError(f"Full arrays leaked in MCP result field {child_key}")
            if child_key == "coordinates" and isinstance(child, dict):
                if any(isinstance(item, list) for item in child.values()):
                    raise VerificationError("Full coordinates leaked in MCP result")
            check_bounded(child, child_key)
    elif isinstance(value, list):
        if len(value) > 32:
            raise VerificationError(f"Unbounded MCP result list: {key}")
        if value and all(isinstance(item, (int, float)) for item in value) and key not in ("shape", "range"):
            raise VerificationError(f"Unexpected numeric array in MCP result: {key}")
        for child in value:
            check_bounded(child, key)
    elif isinstance(value, float) and not math.isfinite(value):
        raise VerificationError(f"Non-finite MCP summary: {key}")


class Verifier:
    def __init__(self, output: Path, report: dict[str, Any]):
        self.output = output
        self.report = report
        self.client = None

    def check(self, condition: bool, message: str) -> None:
        if not condition:
            raise VerificationError(message)
        self.report["checks_passed"] += 1

    def numeric(self, actual, expected, label: str, rtol=1e-12, atol=1e-12) -> None:
        import numpy as np
        actual, expected = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
        self.check(actual.shape == expected.shape, f"{label}: shape mismatch")
        self.check(bool(np.isfinite(actual).all()), f"{label}: non-finite values")
        self.check(bool(np.allclose(actual, expected, rtol=rtol, atol=atol)), f"{label}: numeric mismatch")

    async def call(self, name: str, arguments=None, outputs=None) -> dict[str, Any]:
        result = await self.client.call_tool(name, arguments or {})
        self.check(not result.isError, f"{name} failed: {str(result.content)[:500]}")
        value = result.structuredContent
        self.check(isinstance(value, dict), f"{name}: missing structuredContent object")
        self.check(len(result.content) == 1 and result.content[0].type == "text", f"{name}: unexpected content blocks")
        self.check(json.loads(result.content[0].text) == value, f"{name}: text and structured results differ")
        encoded = json.dumps(value, allow_nan=False).encode("utf-8")
        self.check(len(encoded) <= MAX_RESPONSE_BYTES, f"{name}: oversized MCP response")
        self.check(len(result.content[0].text.encode("utf-8")) <= 2 * MAX_RESPONSE_BYTES, f"{name}: oversized text response")
        check_bounded(value)
        self.report["calls"].append({"tool": name, "expected_error": False, "response_bytes": len(encoded)})
        if outputs is not None:
            self.check(value.get("outputs") == {key: str(path) for key, path in outputs.items()}, f"{name}: output descriptors differ")
            for path in value["outputs"].values():
                target = Path(path)
                self.check(target.is_absolute() and target.is_file(), f"{name}: output path is not an absolute written file")
                self.check(target.resolve().is_relative_to(self.output), f"{name}: output escaped requested directory")
        return value

    async def error(self, name: str, arguments) -> None:
        result = await self.client.call_tool(name, arguments)
        self.check(result.isError is True, f"{name}: expected an MCP tool error")
        self.check(bool(result.content) and all(item.type == "text" and item.text for item in result.content), f"{name}: missing error text")
        self.report["calls"].append({"tool": name, "expected_error": True})


def installed_package(executable: Path, verifier: Verifier) -> dict[str, Any]:
    verifier.check(sys.prefix != sys.base_prefix, "Run the verifier using the installed wheel's venv Python")
    interpreter_dir = Path(sys.executable).absolute().parent.resolve()
    verifier.check(executable.parent == interpreter_dir, "--executable must belong to the verifier Python's venv")
    verifier.check(executable.name in ("ramancloud-mcp", "ramancloud-mcp.exe"), "Select the actual ramancloud-mcp console executable")
    verifier.check(executable.is_file() and os.access(executable, os.X_OK), "MCP console executable is missing or not executable")
    distribution = importlib.metadata.distribution("ramancloud")
    direct_url = json.loads(distribution.read_text("direct_url.json") or "{}")
    verifier.check(not direct_url.get("dir_info", {}).get("editable", False), "Editable installs are not release evidence; install the wheel into a fresh venv")
    verifier.check(distribution.read_text("WHEEL") is not None, "Missing installed wheel metadata")
    scripts = {entry.name: entry.value for entry in distribution.entry_points if entry.group == "console_scripts"}
    verifier.check(scripts.get("ramancloud-mcp") == "ramancloud_mcp.server:main", "Incorrect installed MCP entry point")
    locations = {}
    for name in ("ramancloud_backend.app", "ramancloud_mcp.server"):
        expected = distribution.locate_file(name.replace(".", "/") + ".py").resolve()
        specification = importlib.util.find_spec(name)
        verifier.check(specification is not None and specification.origin is not None, f"Missing installed module: {name}")
        actual = Path(specification.origin).resolve()
        verifier.check(actual == expected and actual.is_relative_to(Path(sys.prefix).resolve()), f"{name}: importing source code instead of the installed wheel")
        locations[name] = str(actual)
    recorded = distribution.files or []
    verifier.check(any(distribution.locate_file(item).resolve() == executable for item in recorded), "Executable is not recorded in the installed distribution")
    return {"version": distribution.version, "python": sys.version.split()[0], "venv": sys.prefix,
            "mcp_sdk": importlib.metadata.version("mcp"), "numpy": importlib.metadata.version("numpy"),
            "pydantic": importlib.metadata.version("pydantic"), "modules": locations,
            "wheel_sha256": direct_url.get("archive_info", {}).get("hashes", {}).get("sha256")}


def table_bytes(rows) -> bytes:
    buffer = io.StringIO()
    csv.writer(buffer, delimiter="\t", lineterminator="\n").writerows(rows)
    return buffer.getvalue().encode("utf-8")


def backend_export(api, wave, data, module, coordinates) -> bytes:
    if module == "spectrum":
        return api.download(api.DownloadPayload(wavenumber=wave.tolist(), intensity=data.tolist())).body
    dataset_id = api.register_dataset(wave, data, module, "expected.tsv", coordinates)
    try:
        return api.download(api.DownloadPayload(wavenumber=wave.tolist(), dataset_id=dataset_id, format="mapping")).body
    finally:
        with api.DATASET_LOCK:
            api.DATASETS.pop(dataset_id, None)


async def verify_tools(verifier: Verifier) -> None:
    import numpy as np
    from ramancloud_backend import app as api
    from ramancloud_backend.algorithms.processing import PARAMETERS

    output = verifier.output
    tools = {tool.name: tool for tool in (await verifier.client.list_tools()).tools}
    verifier.check(set(tools) == TOOL_NAMES, "Installed tool catalog does not contain exactly the expected ten tools")
    verifier.report["tools"] = sorted(tools)
    for name, tool in tools.items():
        verifier.check(tool.inputSchema.get("type") == "object", f"{name}: invalid input schema")
        verifier.check(tool.outputSchema is not None and tool.outputSchema.get("type") == "object", f"{name}: missing structured output schema")
        verifier.check(tool.annotations is not None and tool.annotations.openWorldHint is False, f"{name}: missing local-tool annotation")
        verifier.check(tool.annotations.readOnlyHint == (name in ("inspect_file", "inspect_capabilities")), f"{name}: incorrect read-only annotation")
    caps = await verifier.call("inspect_capabilities")
    verifier.check(caps["modules"] == ["spectrum", "imaging", "time_series"], "Missing main modules")
    for category, methods in (("denoise", api.DENOISE_METHODS), ("baseline", api.BASELINE_METHODS)):
        verifier.check(set(caps["algorithms"][category]) == set(methods), f"{category}: catalog differs from the backend")
        for method in methods:
            for key, (default, kind, minimum, maximum) in PARAMETERS[method].items():
                parameter = caps["algorithms"][category][method][key]
                verifier.check((parameter["default"], parameter["type"], parameter["minimum"], parameter["maximum"]) ==
                               (default, kind.__name__, minimum, maximum), f"{method}.{key}: parameter metadata differs")
    demos = {**{name: filename for name, filename in api.DEMO_SPECTRA.items()},
             **{name: item[0] for name, item in api.DEMO_MAPPING.items()}}
    verifier.check(set(caps["demos"]) == set(demos), "Demo catalog differs from the backend")
    for name, filename in demos.items():
        sample = api.SAMPLES / filename
        verifier.check(sample.is_file() and sample.stat().st_size > 0, f"Packaged demo is missing: {name}")
    demo = output / "bacteria-demo.txt"
    await verifier.call("load_demo", {"name": "bacteria", "output_path": str(demo)}, {"demo": demo})
    verifier.check(demo.read_bytes() == (api.SAMPLES / api.DEMO_SPECTRA["bacteria"]).read_bytes(), "Loaded demo differs from its packaged bytes")
    demo_summary = await verifier.call("inspect_file", {"input_path": str(demo), "module": "spectrum"})
    full_wave, full_data = api.read_spectrum(demo.read_bytes())
    verifier.check(demo_summary["shape"] == list(full_data.shape), "Demo inspection shape differs")
    indices = np.linspace(0, len(full_wave) - 1, min(64, len(full_wave)), dtype=int)
    wave, base = full_wave[indices], full_data[indices]
    verifier.check(len(wave) >= 32, "Demo needs at least 32 points for the lightweight processing fixtures")

    async def workflow(module, source, label, instrument="Horiba"):
        if module == "spectrum":
            input_wave, input_data = api.read_spectrum(source.read_bytes())
            coordinates, reader = {}, api.read_spectrum
        else:
            reader = api.read_imaging if module == "imaging" else api.read_time_series
            input_wave, input_data, coordinates = reader(source.read_bytes(), instrument)
        steps = [{"type": "cut", "params": {"start": float(input_wave[3]), "end": float(input_wave[-4])}},
                 {"type": "denoise", "method": "sg", "params": {"window_size": 5, "order": 2}},
                 {"type": "baseline", "method": "imodpoly", "params": {"poly_order": 2}}]
        flat = input_data.reshape(-1, input_data.shape[-1]) if input_data.ndim == 3 else input_data
        expected_wave, expected, baseline, history = api.apply_pipeline(input_wave, flat, [api.Step(**step) for step in steps])
        shape = (*input_data.shape[:-1], len(expected_wave))
        expected, baseline = expected.reshape(shape), baseline.reshape(shape)
        paths = {"processed": output / f"{label}.tsv", "processing_json": output / f"{label}-processing.json",
                 "baseline": output / f"{label}-baseline.tsv", "summary_json": output / f"{label}-summary.json",
                 "preview": output / f"{label}-preview.svg"}
        arguments = {"input_path": str(source), "output_path": str(paths["processed"]), "steps": steps,
                     "processing_json_path": str(paths["processing_json"]), "baseline_path": str(paths["baseline"]),
                     "summary_path": str(paths["summary_json"]), "preview_path": str(paths["preview"])}
        if module != "spectrum":
            arguments["instrument"] = instrument
        if module == "imaging":
            arguments["preview_wavenumber"] = float(expected_wave[len(expected_wave) // 2])
        summary = await verifier.call(f"process_{module}", arguments, paths)
        verifier.check(summary["shape"] == list(shape) and summary["history"] == history, f"{label}: pipeline summary differs")
        verifier.check(summary["baseline_available"] is True, f"{label}: baseline availability differs")
        for key, array in (("processed", expected), ("baseline", baseline)):
            verifier.check(sniff_format(paths[key]) == "tsv", f"{label}.{key}: expected actual TSV, not a renamed ZIP")
            verifier.check(paths[key].read_bytes() == backend_export(api, expected_wave, array, module, coordinates), f"{label}.{key}: download differs from the backend")
            parsed = reader(paths[key].read_bytes()) if module == "spectrum" else reader(paths[key].read_bytes(), "Horiba")
            verifier.numeric(parsed[0], expected_wave, f"{label}.{key}.wavenumber", rtol=5e-8, atol=5e-8)
            verifier.numeric(parsed[1], array, f"{label}.{key}.values", rtol=5e-8, atol=5e-8)
            if module == "imaging":
                verifier.check(parsed[2] == coordinates, f"{label}.{key}: physical X/Y coordinates changed")
            elif module == "time_series":
                verifier.check(parsed[2]["time"] == coordinates["time"], f"{label}.{key}: time coordinates or order changed")
        full = read_json(paths["processing_json"])
        verifier.check(sniff_format(paths["processing_json"]) == "json" and full["schema_version"] == 1, f"{label}: invalid processing JSON")
        verifier.numeric(full["wavenumber"], expected_wave, f"{label}.json.wavenumber")
        verifier.numeric(full["intensity" if module == "spectrum" else "spectra"], expected, f"{label}.json.values")
        verifier.numeric(full["baseline"], baseline, f"{label}.json.baseline")
        verifier.check(full["coordinates"] == coordinates and full["history"] == history, f"{label}: JSON lost metadata or history")
        verifier.check(read_json(paths["summary_json"]) == summary, f"{label}: summary JSON differs from the MCP result")
        verifier.check(sniff_format(paths["preview"]) == "svg" and ET.parse(paths["preview"]).getroot().tag == "{http://www.w3.org/2000/svg}svg", f"{label}: invalid SVG preview")
        verifier.report["workflows"].append({"module": module, "instrument": instrument, "label": label,
                                           "shape": list(shape), "coordinate_preservation": module != "spectrum"})
        return paths["processed"]

    spectrum = output / "spectrum-input.tsv"
    write_new(spectrum, backend_export(api, wave, base, "spectrum", {}))
    await workflow("spectrum", spectrum, "spectrum")
    batch_inputs, batch_spectra = [], []
    for i in range(5):
        source = output / f"batch-input-{i}.tsv"
        data = base + (i + 1) * np.sin(np.arange(len(base)) * (i + 1))
        write_new(source, backend_export(api, wave, data, "spectrum", {}))
        input_wave, input_data = api.read_spectrum(source.read_bytes())
        batch_inputs.append(source)
        batch_spectra.append(api.BatchSpectrum(filename=source.name, wavenumber=input_wave.tolist(), intensity=input_data.tolist()))
    batch_steps = [{"type": "denoise", "method": "tsvd", "params": {"threshold": 0.6}},
                   {"type": "baseline", "method": "imodpoly", "params": {"poly_order": 2}}]
    expected_batch = api.process_batch(api.BatchPayload(spectra=batch_spectra, steps=[api.Step(**s) for s in batch_steps]))["data"]["spectra"]
    batch_outputs = [output / f"batch-{i}.tsv" for i in range(5)]
    batch_baselines = [output / f"batch-baseline-{i}.tsv" for i in range(5)]
    batch_previews = [output / f"batch-preview-{i}.svg" for i in range(5)]
    batch_paths = {f"processed_{i}": path for i, path in enumerate(batch_outputs)}
    batch_paths.update({f"baseline_{i}": path for i, path in enumerate(batch_baselines)})
    batch_paths.update({f"preview_{i}": path for i, path in enumerate(batch_previews)})
    batch_paths.update(processing_json=output / "batch-processing.json", summary_json=output / "batch-summary.json")
    batch_summary = await verifier.call("process_batch", {
        "input_paths": [str(p) for p in batch_inputs], "output_paths": [str(p) for p in batch_outputs], "steps": batch_steps,
        "baseline_paths": [str(p) for p in batch_baselines], "preview_paths": [str(p) for p in batch_previews],
        "processing_json_path": str(batch_paths["processing_json"]), "summary_path": str(batch_paths["summary_json"])}, batch_paths)
    verifier.check(batch_summary["spectrum_count"] == 5, "Batch spectrum count differs")
    verifier.check(read_json(batch_paths["summary_json"]) == batch_summary, "Batch summary JSON differs")
    batch_json = read_json(batch_paths["processing_json"])
    verifier.check(batch_json["schema_version"] == 1 and len(batch_json["results"]) == 5, "Batch processing JSON has incorrect version or count")
    for i, item in enumerate(expected_batch):
        full = batch_json["results"][i]
        verifier.numeric(full["wavenumber"], item["wavenumber"], f"batch-{i}.wavenumber")
        verifier.numeric(full["intensity"], item["intensity"], f"batch-{i}.values")
        verifier.numeric(full["baseline"], item["baseline"], f"batch-{i}.baseline")
        verifier.check(full["history"] == item["history"], f"batch-{i}: joint TSVD history differs")
        for path, values in ((batch_outputs[i], item["intensity"]), (batch_baselines[i], item["baseline"])):
            verifier.check(sniff_format(path) == "tsv", f"batch-{i}: invalid TSV output")
            verifier.check(path.read_bytes() == backend_export(api, np.asarray(item["wavenumber"]), np.asarray(values), "spectrum", {}), f"batch-{i}: API batch/download parity failure")
        verifier.check(ET.parse(batch_previews[i]).getroot().tag.endswith("svg"), f"batch-{i}: invalid preview")
    verifier.report["workflows"].append({"module": "batch", "spectra": 5, "joint_tsvd": True})

    time_source = output / "time-input.tsv"
    write_new(time_source, table_bytes([["", *wave], *[[time, *(base + i)] for i, time in enumerate([9.25, 2.5, 20.875])]]))
    await workflow("time_series", time_source, "time-horiba")
    nano_time = output / "nanophoton-time-input.tsv"
    labels = ["2026/10/3 12:00:17 Cycle:2", "2026/10/3 12:00:05 Cycle:1", "2026/10/3 12:00:00 Cycle:0"]
    header = [cell for i, label in enumerate(labels) for cell in (f"WN{i}", label)]
    rows = [[cell for i in range(3) for cell in (w, base[j] + 2 - i)] for j, w in enumerate(wave)]
    write_new(nano_time, table_bytes([header, *rows]))
    await workflow("time_series", nano_time, "time-nanophoton", "Nanophoton")
    verifier.check(read_json(output / "time-nanophoton-processing.json")["coordinates"]["time_labels"] == labels[::-1], "Nanophoton original time labels were lost")
    renishaw = output / "renishaw-time-input.tsv"
    write_new(renishaw, table_bytes([[time, w, value + i] for i, time in enumerate([11.25, 2.75, 7.5]) for w, value in zip(wave, base)]))
    await workflow("time_series", renishaw, "time-renishaw", "Renishaw")
    imaging_source = output / "imaging-input.tsv"
    positions = [(20.75, 9.875), (-3.5, 4.125), (8.25, 9.875), (20.75, 4.125), (-3.5, 9.875), (8.25, 4.125)]
    write_new(imaging_source, table_bytes([["", "", *wave], *[[x, y, *(base + i)] for i, (x, y) in enumerate(positions)]]))
    imaging = await workflow("imaging", imaging_source, "imaging-horiba")

    archive_path = output / "imaging-split.txt"
    split = await verifier.call("split_mapping", {"input_path": str(imaging), "output_path": str(archive_path)}, {"archive": archive_path})
    verifier.check(sniff_format(archive_path) == "zip", "ZIP output must be identified by content even with a .txt extension")
    expected_zip = api.split_mapping_file(imaging.read_bytes(), "Horiba", imaging.name)
    split_inputs = []
    with zipfile.ZipFile(archive_path) as actual, zipfile.ZipFile(io.BytesIO(expected_zip)) as expected:
        verifier.check(actual.testzip() is None and actual.namelist() == expected.namelist(), "Split archive members or CRC checks differ")
        verifier.check(len(actual.namelist()) == split["spectrum_count"] == 6, "Split spectrum count differs")
        for i, name in enumerate(actual.namelist()):
            content = actual.read(name)
            verifier.check(content == expected.read(name), f"Split spectrum {i}: backend parity failure")
            member = output / f"split-spectrum-{i}.tsv"
            write_new(member, content)
            member_wave, member_data = api.read_spectrum(content)
            verifier.check(member_data.ndim == 1 and len(member_wave) == len(member_data), f"Split spectrum {i}: invalid numeric format")
            split_inputs.append(member)
    verifier.report["zip_sniffing"] = {"file": str(archive_path), "suffix": ".txt", "detected": "zip", "crc_valid": True}
    await verifier.error("inspect_file", {"input_path": str(archive_path), "module": "imaging"})
    merged = output / "merged.tsv"
    await verifier.call("merge_spectra", {"input_paths": [str(p) for p in split_inputs], "output_path": str(merged)}, {"merged": merged})
    expected_merge = api.merge_spectrum_files([(p.name, p.read_bytes()) for p in split_inputs])
    verifier.check(sniff_format(merged) == "tsv" and merged.read_bytes() == expected_merge, "Merged output is not the backend matrix TSV")
    merge_matrix = np.loadtxt(merged, delimiter="\t")
    first_wave, _ = api.read_spectrum(split_inputs[0].read_bytes())
    verifier.check(merge_matrix.shape == (len(first_wave), 7), "Merged matrix must have one axis and six spectrum columns")
    verifier.numeric(merge_matrix[:, 0], first_wave, "merged.wavenumber")
    for i, source in enumerate(split_inputs):
        verifier.numeric(merge_matrix[:, i + 1], api.read_spectrum(source.read_bytes())[1], f"merged.spectrum-{i}")

    nano, back = output / "converted-nanophoton.tsv", output / "converted-horiba.tsv"
    await verifier.call("convert_mapping", {"input_path": str(imaging), "output_path": str(nano), "conversion": "horiba_to_nanophoton"}, {"converted": nano})
    verifier.check(nano.read_bytes() == api.horiba_to_nanophoton(imaging.read_bytes()), "Horiba to Nanophoton conversion parity failure")
    converted_wave, converted_data, converted_coords = api.read_imaging(nano.read_bytes(), "Nanophoton")
    original_wave, original_data, _ = api.read_imaging(imaging.read_bytes(), "Horiba")
    verifier.numeric(converted_wave, np.round(np.sort(original_wave), 1), "converted.wavenumber")
    expected_order = original_data if original_wave[0] <= original_wave[-1] else original_data[:, :, ::-1]
    verifier.numeric(converted_data, np.round(expected_order, 1), "converted.values")
    verifier.check(converted_coords == {"x": [0.0, 1.0, 2.0], "y": [0.0, 1.0]}, "Conversion must match the backend's zero-based indices")
    await verifier.call("convert_mapping", {"input_path": str(nano), "output_path": str(back), "conversion": "nanophoton_to_horiba"}, {"converted": back})
    verifier.check(back.read_bytes() == api.nanophoton_to_horiba(nano.read_bytes()), "Nanophoton to Horiba conversion parity failure")
    back_wave, back_data, back_coords = api.read_imaging(back.read_bytes(), "Horiba")
    verifier.numeric(back_wave, converted_wave, "conversion round-trip.wavenumber")
    verifier.numeric(back_data, converted_data, "conversion round-trip.values")
    verifier.check(back_coords == converted_coords, "Conversion round-trip grid indices differ")
    await workflow("imaging", nano, "imaging-nanophoton", "Nanophoton")

    original = spectrum.read_bytes()
    digest = hashlib.sha256(demo.read_bytes()).hexdigest()
    await verifier.error("load_demo", {"name": "bacteria", "output_path": str(demo)})
    verifier.check(hashlib.sha256(demo.read_bytes()).hexdigest() == digest, "Default overwrite refusal modified an existing file")
    await verifier.error("process_spectrum", {"input_path": str(spectrum), "output_path": str(spectrum), "overwrite": True})
    verifier.check(spectrum.read_bytes() == original, "Input/output alias refusal modified the input")
    await verifier.call("inspect_file", {"input_path": str(imaging), "module": "imaging"})
    verifier.check({entry["tool"] for entry in verifier.report["calls"] if not entry["expected_error"]} == TOOL_NAMES, "Not all ten tools were called successfully")


async def run(executable: Path, verifier: Verifier) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    verifier.report["package"] = installed_package(executable, verifier)
    with tempfile.TemporaryDirectory(prefix="ramancloud-mcp-unrelated-cwd-") as cwd:
        verifier.report["server_cwd"] = cwd
        params = StdioServerParameters(command=str(executable), cwd=cwd, env={
            "PYTHONPATH": "", "PYTHONNOUSERSITE": "1", "PYTHONSAFEPATH": "1",
        })
        with (verifier.output / "server.stderr.log").open("x", encoding="utf-8") as stderr:
            async with stdio_client(params, errlog=stderr) as (reader, writer):
                async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=120)) as client:
                    initialized = await client.initialize()
                    verifier.check(initialized.serverInfo.name == "RamanCloud", "Unexpected MCP server identity")
                    verifier.report["protocol_version"] = initialized.protocolVersion
                    verifier.client = client
                    await verify_tools(verifier)
        verifier.check(not any(Path(cwd).iterdir()), "Server created unsolicited files in its unrelated working directory")


def error_message(error: Exception) -> str:
    if isinstance(error, BaseExceptionGroup):
        return "; ".join(error_message(child) for child in error.exceptions)[:1000]
    return f"{type(error).__name__}: {error}"[:1000]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--executable", required=True, type=Path, help="Installed ramancloud-mcp console script in the verifier's fresh venv")
    parser.add_argument("--output-dir", required=True, type=Path, help="Empty or absent directory for artifacts, logs, and verification.json")
    args = parser.parse_args(argv)
    output = args.output_dir.expanduser().resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error("--output-dir must be an empty or absent directory; existing evidence is never overwritten")
    output.mkdir(parents=True, exist_ok=True)
    executable = args.executable.expanduser().resolve()
    report = {"status": "running", "executable": str(executable), "output_dir": str(output),
              "checks_passed": 0, "tools": [], "calls": [], "workflows": []}
    verifier = Verifier(output, report)
    try:
        asyncio.run(run(executable, verifier))
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = error_message(exc)
        print(report["error"], file=sys.stderr)
    report_path = output / "verification.json"
    write_new(report_path, (json.dumps(report, allow_nan=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({"status": report["status"], "tools": len(report["tools"]),
                      "calls": len(report["calls"]), "checks_passed": report["checks_passed"],
                      "report": str(report_path)}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
