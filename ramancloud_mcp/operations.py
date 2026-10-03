"""Adapters and artifact serialization; all Raman algorithms live in the backend."""

import importlib
import io
import json
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal
from xml.etree import ElementTree as ET

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from .files import FilePlan, input_file

Module = Literal["spectrum", "imaging", "time_series"]
Instrument = Literal["Horiba", "Nanophoton", "Renishaw"]
MAX_BATCH = 100
MAX_STEPS = 32
MAX_BATCH_SUMMARIES = 8


class PipelineStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["cut", "denoise", "baseline"]
    method: str = "skip"
    params: dict[str, Any] = Field(default_factory=dict)


@lru_cache(maxsize=1)
def core():
    return importlib.import_module("ramancloud_backend.app")


def backend_steps(steps: list[PipelineStep] | None):
    if len(steps or []) > MAX_STEPS:
        raise ValueError(f"At most {MAX_STEPS} pipeline steps are accepted")
    return [core().Step(**PipelineStep.model_validate(step).model_dump()) for step in steps or []]


def axis_summary(values) -> dict[str, Any]:
    axis = np.asarray(values, dtype=float)
    return {"count": int(axis.size), "min": float(axis.min()), "max": float(axis.max()),
            "first": float(axis.flat[0]), "last": float(axis.flat[-1])}


def summarize(wave, data, module: str, coordinates=None, history=None) -> dict[str, Any]:
    array = np.asarray(data, dtype=float)
    scale = float(np.abs(array).max())
    mean = float((array / scale).mean() * scale) if scale else 0.0
    result = {"module": module, "shape": list(array.shape), "wavenumber": axis_summary(wave),
              "spectrum_count": int(array.size // len(wave)),
              "intensity": {"min": float(array.min()), "max": float(array.max()),
                            "mean": mean}}
    if coordinates:
        result["coordinates"] = {
            key: axis_summary(value) if key in ("x", "y", "time") else
            {"count": len(value)} if key == "time_labels" else value
            for key, value in coordinates.items()
        }
    if history is not None:
        result["history"] = history
    return result


def inspect_capabilities() -> dict[str, Any]:
    api = core()
    processing = importlib.import_module("ramancloud_backend.algorithms.processing")
    algorithms = {}
    for category, methods in (("denoise", api.DENOISE_METHODS), ("baseline", api.BASELINE_METHODS)):
        algorithms[category] = {
            method: {key: {"default": default, "type": kind.__name__, "minimum": minimum,
                           "maximum": maximum, **({"choices": [f"db{i}" for i in range(1, 10)]}
                                                   if key == "wavelet" else {})}
                     for key, (default, kind, minimum, maximum) in processing.PARAMETERS[method].items()}
            for method in methods
        }
    demos = {name: {"module": "spectrum", "filename": filename}
             for name, filename in api.DEMO_SPECTRA.items()}
    demos.update({name: {"filename": filename, "instrument": instrument, "module": module}
                  for name, (filename, instrument, module) in api.DEMO_MAPPING.items()})
    return {
        "modules": ["spectrum", "imaging", "time_series"],
        "formats": {
            "spectrum": "Numeric TXT/TSV, CSV, or whitespace; optional header lines; backend column selection applies",
            "imaging": {"Horiba": "TSV: empty X/Y header cells, then wavenumbers; rows X,Y,intensities",
                        "Nanophoton": "TSV: Wavenumber and xN_yN columns"},
            "time_series": {"Horiba": "TSV: empty time header cell, then wavenumbers; rows time,intensities",
                            "Nanophoton": "TSV: alternating wavenumber/intensity pairs with scan or timestamp headers",
                            "Renishaw": "TSV: time,wavenumber,intensity rows"},
        },
        "algorithms": algorithms,
        "cut": {"start": "Inclusive lower/upper bound; defaults to axis minimum",
                "end": "Inclusive upper/lower bound; defaults to axis maximum"},
        "aliases": {"savitzky_golay": "sg", "lambda_": "lam", "order_": "diff_order"},
        "constraints": ["SG: odd window <= spectral length; polynomial order < window",
                        "WTD: level <= wavelet maximum for the input length",
                        "TSVD: batch/mapping only; batch axes must be identical",
                        "PEER: at least 7 points", "AABS: at least max(100,Ln,Lb) points",
                        "SNIP: max_half_window <= (spectral length-1)//2",
                        "Imaging: complete, unique rectangular X/Y grid; output order is [Y,X,wavenumber]"],
        "demos": demos,
        "outputs": {"spectrum": "Backend two-column TSV", "batch": "One backend TSV per explicit output path",
                    "imaging": "Coordinate-preserving Horiba TSV", "time_series": "Coordinate-preserving Horiba TSV",
                    "optional": ["processing JSON with full arrays/metadata", "baseline TSV", "summary JSON", "SVG preview"]},
        "limits": {"batch_files": MAX_BATCH, "pipeline_steps": MAX_STEPS,
                   "batch_summaries_returned": MAX_BATCH_SUMMARIES, "preview_cells_per_axis": 96},
        "file_policy": "Only explicit input/output paths and named packaged demos; existing output parents required; no overwrite by default; never replace inputs",
        "conversion_notes": "Split/merge/conversion match the backend, including rounding and conversion to zero-based coordinate indices; merge emits a wavenumber-plus-spectra matrix, not a Horiba coordinate mapping",
    }


def read(content: bytes, module: Module, instrument: Instrument):
    api = core()
    if module == "spectrum":
        wave, data = api.read_spectrum(content)
        return wave, data, {}
    if module == "imaging":
        return api.read_imaging(content, instrument)
    if module == "time_series":
        return api.read_time_series(content, instrument)
    raise ValueError(f"Unsupported module: {module}")


def inspect_file(input_path: str, module: Module, instrument: Instrument = "Horiba"):
    source = input_file(input_path)
    wave, data, coordinates = read(source.read_bytes(), module, instrument)
    return {"input_path": str(source), **summarize(wave, data, module, coordinates)}


def load_demo(name: str, output_path: str, overwrite: bool = False):
    api = core()
    if name in api.DEMO_SPECTRA:
        filename, instrument, module = api.DEMO_SPECTRA[name], "Horiba", "spectrum"
    elif name in api.DEMO_MAPPING:
        filename, instrument, module = api.DEMO_MAPPING[name]
    else:
        raise ValueError("Unknown demo; inspect_capabilities lists available names")
    source = input_file(str(api.SAMPLES / filename))
    plan = FilePlan([source], {"demo": output_path}, overwrite)
    content = source.read_bytes()
    wave, data, coordinates = read(content, module, instrument)
    summary = {"demo": name, "instrument": instrument, **summarize(wave, data, module, coordinates)}
    plan.write({"demo": content})
    return {**summary, "outputs": plan.written_paths()}


@dataclass
class Processed:
    module: str
    wave: np.ndarray
    data: np.ndarray
    coordinates: dict[str, Any]
    baseline: np.ndarray | None
    history: list[dict[str, Any]]

    def summary(self):
        return {**summarize(self.wave, self.data, self.module, self.coordinates, self.history),
                "baseline_available": self.baseline is not None}

    def json(self):
        return {"module": self.module, "wavenumber": self.wave.tolist(),
                "intensity" if self.module == "spectrum" else "spectra": self.data.tolist(),
                "coordinates": self.coordinates,
                "baseline": self.baseline.tolist() if self.baseline is not None else None,
                "history": self.history}


def export_tsv(result: Processed, baseline: bool = False) -> bytes:
    api = core()
    data = result.baseline if baseline else result.data
    if data is None:
        raise ValueError("A baseline output was requested, but the pipeline produced no baseline")
    if result.module == "spectrum":
        return api.download(api.DownloadPayload(wavenumber=result.wave.tolist(), intensity=data.tolist())).body
    dataset_id = api.register_dataset(result.wave, data, result.module, "mcp.tsv", result.coordinates)
    try:
        return api.download(api.DownloadPayload(wavenumber=result.wave.tolist(), dataset_id=dataset_id,
                                                format="mapping")).body
    finally:
        with api.DATASET_LOCK:
            api.DATASETS.pop(dataset_id, None)


def json_bytes(value) -> bytes:
    return (json.dumps(value, allow_nan=False, ensure_ascii=True, indent=2) + "\n").encode("utf-8")


def preview_svg(result: Processed, target: float | None = None) -> bytes:
    root = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "viewBox": "0 0 800 480",
                              "role": "img", "aria-label": f"Processed {result.module} preview"})
    ET.SubElement(root, "rect", {"width": "800", "height": "480", "fill": "white"})

    def label(x, y, value):
        ET.SubElement(root, "text", {"x": str(x), "y": str(y), "font-family": "sans-serif",
                                     "font-size": "14", "fill": "#202428"}).text = str(value)

    label(60, 28, f"Processed {result.module}")
    if result.module == "spectrum":
        indexes = np.linspace(0, len(result.wave) - 1, min(1024, len(result.wave)), dtype=int)
        wave, values = result.wave[indexes], result.data[indexes]
        xmin, xmax, ymin, ymax = wave.min(), wave.max(), values.min(), values.max()
        xs = 60 + 700 * (wave - xmin) / (float(xmax - xmin) or 1)
        ys = 410 - 340 * (values - ymin) / (float(ymax - ymin) or 1)
        ET.SubElement(root, "polyline", {"points": " ".join(f"{x:.3f},{y:.3f}" for x, y in zip(xs, ys)),
                                         "fill": "none", "stroke": "#007f75", "stroke-width": "2"})
        label(60, 445, f"Wavenumber: {xmin:.7g} to {xmax:.7g}")
        label(60, 465, f"Intensity: {ymin:.7g} to {ymax:.7g}")
    else:
        if target is not None and not np.isfinite(target):
            raise ValueError("Preview wavenumber must be finite")
        preview, wave, _, _ = core().heatmap_slice(result.wave, result.data, target)
        matrix = np.asarray(preview)
        rows = np.linspace(0, matrix.shape[0] - 1, min(96, matrix.shape[0]), dtype=int)
        cols = np.linspace(0, matrix.shape[1] - 1, min(96, matrix.shape[1]), dtype=int)
        matrix = matrix[np.ix_(rows, cols)]
        low, high = float(matrix.min()), float(matrix.max())
        scaled = (matrix - low) / (high - low or 1)
        width, height = 700 / len(cols), 340 / len(rows)
        for y, row in enumerate(scaled):
            for x, value in enumerate(row):
                red, green, blue = int(35 + 210 * value), int(170 - 100 * value), int(185 - 120 * value)
                ET.SubElement(root, "rect", {"x": f"{60 + x * width:.3f}", "y": f"{65 + y * height:.3f}",
                                             "width": f"{width:.3f}", "height": f"{height:.3f}",
                                             "fill": f"rgb({red},{green},{blue})"})
        if result.module == "imaging":
            label(60, 445, f"X: {result.coordinates['x'][0]:.7g} to {result.coordinates['x'][-1]:.7g}; "
                          f"Y: {result.coordinates['y'][0]:.7g} to {result.coordinates['y'][-1]:.7g}; Wavenumber: {wave:.7g}")
        else:
            times = result.coordinates["time"]
            label(60, 445, f"Wavenumber: {result.wave[0]:.7g} to {result.wave[-1]:.7g}; "
                          f"Time/index: {times[0]:.7g} to {times[-1]:.7g}")
        label(60, 465, f"Intensity: {low:.7g} to {high:.7g}")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def processing_plan(inputs, output_path, processing_json_path, baseline_path, summary_path, preview_path, overwrite):
    if preview_path is not None and not preview_path.lower().endswith(".svg"):
        raise ValueError("Preview output path must end in .svg")
    return FilePlan(inputs, {"processed": output_path, "processing_json": processing_json_path,
                             "baseline": baseline_path, "summary_json": summary_path, "preview": preview_path}, overwrite)


def artifacts(result: Processed, plan: FilePlan, source: str, preview_wavenumber=None):
    summary = {"input_path": source, **result.summary(), "outputs": plan.written_paths()}
    contents = {"processed": export_tsv(result)}
    if "baseline" in plan.paths:
        contents["baseline"] = export_tsv(result, baseline=True)
    if "processing_json" in plan.paths:
        contents["processing_json"] = json_bytes({"schema_version": 1, "input_path": source, **result.json()})
    if "summary_json" in plan.paths:
        contents["summary_json"] = json_bytes(summary)
    if "preview" in plan.paths:
        contents["preview"] = preview_svg(result, preview_wavenumber)
    plan.write(contents)
    return summary


def process_file(input_path: str, output_path: str, module: Module, instrument: Instrument,
                 steps=None, processing_json_path=None, baseline_path=None, summary_path=None,
                 preview_path=None, overwrite=False, preview_wavenumber=None):
    source = input_file(input_path)
    plan = processing_plan([source], output_path, processing_json_path, baseline_path, summary_path, preview_path, overwrite)
    wave, data, coordinates = read(source.read_bytes(), module, instrument)
    matrix = data.reshape(-1, data.shape[-1]) if data.ndim == 3 else data
    wave, processed, baseline, history = core().apply_pipeline(wave, matrix, backend_steps(steps))
    shape = (*data.shape[:-1], len(wave))
    result = Processed(module, wave, processed.reshape(shape), coordinates,
                       baseline.reshape(shape) if baseline is not None else None, history)
    return artifacts(result, plan, str(source), preview_wavenumber)


def process_batch(input_paths: list[str], output_paths: list[str], steps=None,
                  processing_json_path=None, baseline_paths=None, summary_path=None,
                  preview_paths=None, overwrite=False):
    if not 1 <= len(input_paths) <= MAX_BATCH:
        raise ValueError(f"Batch processing accepts 1 to {MAX_BATCH} explicit input paths")
    if len(output_paths) != len(input_paths):
        raise ValueError("Provide one explicit output path per input, in the same order")
    sources = [input_file(path) for path in input_paths]
    slots = {f"processed_{i}": path for i, path in enumerate(output_paths)}
    for prefix, paths in (("baseline", baseline_paths), ("preview", preview_paths)):
        if paths is None:
            continue
        if len(paths) != len(sources):
            raise ValueError(f"Provide one {prefix} path per input")
        for i, path in enumerate(paths):
            if prefix == "preview" and not path.lower().endswith(".svg"):
                raise ValueError("Preview output paths must end in .svg")
            slots[f"{prefix}_{i}"] = path
    slots.update(processing_json=processing_json_path, summary_json=summary_path)
    plan = FilePlan(sources, slots, overwrite)
    api = core()
    spectra = []
    for source in sources:
        wave, data = api.read_spectrum(source.read_bytes())
        spectra.append(api.BatchSpectrum(filename=source.name, wavenumber=wave.tolist(), intensity=data.tolist()))
    processed = api.process_batch(api.BatchPayload(spectra=spectra, steps=backend_steps(steps)))["data"]["spectra"]
    results = [Processed("spectrum", np.asarray(item["wavenumber"]), np.asarray(item["intensity"]), {},
                         np.asarray(item["baseline"]) if item["baseline"] is not None else None, item["history"])
               for item in processed]
    summaries = [{"input_path": str(source), **result.summary()} for source, result in zip(sources, results)]
    summary = {"module": "batch", "spectrum_count": len(results), "outputs": plan.written_paths(),
               "results": summaries[:MAX_BATCH_SUMMARIES], "results_truncated": len(results) > MAX_BATCH_SUMMARIES}
    contents = {f"processed_{i}": export_tsv(result) for i, result in enumerate(results)}
    for i, result in enumerate(results):
        if f"baseline_{i}" in plan.paths:
            contents[f"baseline_{i}"] = export_tsv(result, baseline=True)
        if f"preview_{i}" in plan.paths:
            contents[f"preview_{i}"] = preview_svg(result)
    if "processing_json" in plan.paths:
        contents["processing_json"] = json_bytes({"schema_version": 1, "module": "batch",
            "results": [{"input_path": str(source), **result.json()} for source, result in zip(sources, results)]})
    if "summary_json" in plan.paths:
        contents["summary_json"] = json_bytes(summary)
    plan.write(contents)
    return summary


def split_mapping(input_path: str, output_path: str, instrument: Instrument = "Horiba", overwrite=False):
    source = input_file(input_path)
    plan = FilePlan([source], {"archive": output_path}, overwrite)
    content = core().split_mapping_file(source.read_bytes(), instrument, source.name)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        count = len(archive.infolist())
    plan.write({"archive": content})
    return {"input_path": str(source), "spectrum_count": count, "outputs": plan.written_paths()}


def merge_spectra(input_paths: list[str], output_path: str, overwrite=False):
    if not 1 <= len(input_paths) <= MAX_BATCH:
        raise ValueError(f"Merge accepts 1 to {MAX_BATCH} explicit input paths")
    sources = [input_file(path) for path in input_paths]
    plan = FilePlan(sources, {"merged": output_path}, overwrite)
    content = core().merge_spectrum_files([(source.name, source.read_bytes()) for source in sources])
    plan.write({"merged": content})
    return {"spectrum_count": len(sources), "format": "wavenumber-plus-spectra matrix TSV", "outputs": plan.written_paths()}


def convert_mapping(input_path: str, output_path: str, conversion: str, overwrite=False):
    source = input_file(input_path)
    plan = FilePlan([source], {"converted": output_path}, overwrite)
    api = core()
    converters = {"horiba_to_nanophoton": api.horiba_to_nanophoton, "nanophoton_to_horiba": api.nanophoton_to_horiba}
    if conversion not in converters:
        raise ValueError("Unsupported conversion")
    content = converters[conversion](source.read_bytes())
    plan.write({"converted": content})
    return {"input_path": str(source), "conversion": conversion, "outputs": plan.written_paths(),
            "note": "Backend conversion uses zero-based coordinate indices and rounds numeric output to one decimal"}
