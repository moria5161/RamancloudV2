"""
RamanCloud preprocessing API.

FastAPI service for spectrum, time-series, and hyperspectral Raman preprocessing.
The original Streamlit site remains untouched in /media/ramancloud.
"""

import io
import re
import uuid
import zipfile
import asyncio
import time
from threading import RLock
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pywt
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field
from algorithms.processing import denoise, denoise_batch, correct_baseline, validated_parameters, DENOISE_METHODS, BASELINE_METHODS


ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"

app = FastAPI(
    title="RamanCloud Preprocessing API",
    version="2.1.0",
    description="Cut, denoise, and baseline-correct Raman spectra and spectral cubes.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Step(BaseModel):
    type: str
    method: str = "skip"
    params: Dict[str, Any] = Field(default_factory=dict)


class SpectrumPayload(BaseModel):
    wavenumber: List[float]
    intensity: List[float]
    steps: List[Step] = Field(default_factory=list)


class CubePayload(BaseModel):
    wavenumber: List[float]
    spectra: Optional[Any] = None
    dataset_id: Optional[str] = None
    shape: Optional[List[int]] = None
    mode: str = "spectra"
    steps: List[Step] = Field(default_factory=list)


class BatchSpectrum(SpectrumPayload):
    filename: str = 'spectrum.txt'


class BatchPayload(BaseModel):
    spectra: List[BatchSpectrum]
    steps: List[Step] = Field(default_factory=list)


class DownloadPayload(BaseModel):
    wavenumber: List[float]
    intensity: Optional[List[float]] = None
    spectra: Optional[Any] = None
    dataset_id: Optional[str] = None
    shape: Optional[List[int]] = None
    mode: str = "spectrum"
    baseline: Optional[List[float]] = None
    filename: str = "processed.txt"
    format: str = "matrix"


DEMO_SPECTRA = {
    "bacteria": "Bacteria.txt",
    "ulf": "ULF.txt",
    "tutorial": "tutorial_raman.txt",
}

DEMO_MAPPING = {
    "timeseries_horiba": ("time_series_Horiba.txt", "Horiba", "time_series"),
    "timeseries_nanophoton": ("time_series_Nanophoton.txt", "Nanophoton", "time_series"),
    "imaging_horiba": ("imaging_Horiba_Graphene.txt", "Horiba", "imaging"),
    "imaging_nanophoton": ("imaging_Nanophoton_Hela.txt", "Nanophoton", "imaging"),
}

DATASETS: Dict[str, Dict[str, Any]] = {}
DATASET_LOCK = RLock()
DATASET_TTL_SECONDS = 1800
DATASET_MAX_BYTES = 1024 * 1024 * 1024


@app.exception_handler(ValueError)
async def parameter_error(request, error):
    return JSONResponse(status_code=400, content={'detail': str(error)})


def purge_datasets():
    with DATASET_LOCK:
        now = time.monotonic()
        for key in list(DATASETS):
            if now - DATASETS[key]['last_access'] >= DATASET_TTL_SECONDS:
                del DATASETS[key]


def get_dataset(dataset_id):
    purge_datasets()
    with DATASET_LOCK:
        if dataset_id not in DATASETS:
            raise HTTPException(status_code=404, detail='Dataset not found or expired. Please reload your file.')
        DATASETS[dataset_id]['last_access'] = time.monotonic()
        return DATASETS[dataset_id]


@app.on_event('startup')
async def start_cleanup():
    async def cleanup():
        while True:
            await asyncio.sleep(60)
            purge_datasets()
    app.state.cleanup_task = asyncio.create_task(cleanup())


@app.on_event('shutdown')
async def stop_cleanup():
    task = getattr(app.state, 'cleanup_task', None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@app.delete('/api/datasets/{dataset_id}')
def delete_dataset(dataset_id: str):
    with DATASET_LOCK:
        DATASETS.pop(dataset_id, None)
    return {'code': 0, 'msg': 'Dataset released'}


def clean_floats(values: Any) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise ValueError("empty numeric array")
    if not np.isfinite(arr).all():
        raise ValueError('Numeric data must be finite')
    return arr


def read_spectrum(content: bytes) -> Tuple[np.ndarray, np.ndarray]:
    if content.startswith(b"\xef\xbb\xbf"):
        content = content[3:]
    pattern = re.compile(rb"^\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)")
    rows = [line for line in content.splitlines() if pattern.match(line)]
    if not rows:
        raise ValueError("No numeric spectrum rows found.")

    first = rows[0]
    if b"\t" in first:
        sep = "\t"
    elif b"," in first:
        sep = ","
    else:
        sep = r"\s+"

    df = pd.read_csv(io.BytesIO(b"\n".join(rows)), sep=sep, header=None, engine="python")
    df = df.dropna(axis=1, how="all")
    if df.shape[1] < 2:
        raise ValueError("Spectrum files need at least two numeric columns.")
    if df.shape[1] >= 4:
        wave = df.iloc[:, -2].values.astype(float)
    else:
        wave = df.iloc[:, 0].values.astype(float)
    intensity = df.iloc[:, -1].values.astype(float)
    if not np.isfinite(wave).all() or not np.isfinite(intensity).all():
        raise ValueError("Spectrum contains missing or non-finite values.")
    return wave, intensity


def validate_mapping(wavenumber: np.ndarray, data: np.ndarray) -> None:
    if not wavenumber.size or not data.size or data.shape[-1] != len(wavenumber):
        raise ValueError("Spectral columns do not match the wavenumber axis.")
    if not np.isfinite(wavenumber).all() or not np.isfinite(data).all():
        raise ValueError("Mapping contains missing or non-finite spectral values.")


def time_coordinates(values: Any, kind: str = "time") -> Dict[str, Any]:
    values = np.asarray(values, dtype=float)
    if not np.isfinite(values).all() or len(np.unique(values)) != len(values):
        raise ValueError("Time coordinates must be finite and unique.")
    return {"time": values.tolist(), "time_kind": kind}


def read_horiba_table(content: bytes, coordinate_columns: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    df = pd.read_csv(io.BytesIO(content), sep="\t", header=None)
    if df.iloc[0, :coordinate_columns].notna().any():
        raise ValueError("Horiba wavenumber header must start with empty coordinate cells.")
    header = df.iloc[0, coordinate_columns:]
    missing = header.index[header.isna()]
    if df.iloc[1:].loc[:, missing].notna().any().any():
        raise ValueError("An intensity column has no wavenumber in the Horiba header.")
    columns = header.index[header.notna()]
    wave = header.loc[columns].values.astype(float)
    data = df.iloc[1:].loc[:, columns].values.astype(float)
    coords = df.iloc[1:, :coordinate_columns].values.astype(float)
    validate_mapping(wave, data)
    return wave, data, coords


def read_time_series(content: bytes, instrument: str) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    if instrument == "Horiba":
        wavenumber, data, coords = read_horiba_table(content, 1)
        return wavenumber, data, time_coordinates(coords[:, 0])

    if instrument == "Renishaw":
        df = pd.read_csv(io.BytesIO(content), sep="\t", header=None)
        if df.shape[1] < 3:
            raise ValueError("Renishaw time series requires time, wavenumber, intensity columns.")
        df = df.iloc[:, :3]
        df.columns = ["time", "wavenumber", "intensity"]
        if df.duplicated(["time", "wavenumber"]).any():
            raise ValueError("Duplicate time/wavenumber pairs in Renishaw file.")
        pivot = df.pivot_table(index="time", columns="wavenumber", values="intensity", aggfunc="first")
        wave, data = pivot.columns.values.astype(float), pivot.values.astype(float)
        validate_mapping(wave, data)
        return wave, data, time_coordinates(pivot.index.values)

    if instrument == "Nanophoton":
        df = pd.read_csv(io.BytesIO(content), sep="\t")
        wavenumber = df.iloc[:, 0].values.astype(float)
        data_cols = np.arange(1, df.shape[1], 2)
        data = df.iloc[:, data_cols].values.astype(float).T[::-1]
        validate_mapping(wavenumber, data)
        labels = [str(df.columns[i]) for i in data_cols][::-1]
        matches = [re.fullmatch(r"(\d{4}/\d{1,2}/\d{1,2} \d{1,2}:\d{2}:\d{2})(?: Cycle:\d+)?", label) for label in labels]
        coordinates = time_coordinates(np.arange(data.shape[0]), "index")
        if all(matches):
            timestamps = pd.to_datetime([match.group(1) for match in matches], format="%Y/%m/%d %H:%M:%S", errors="coerce")
            if not timestamps.isna().any():
                coordinates = time_coordinates((timestamps - timestamps[0]).total_seconds())
                coordinates["time_unit"] = "s"
        coordinates["time_labels"] = labels
        return wavenumber, data, coordinates

    raise ValueError(f"Unsupported instrument: {instrument}")


def extract_xy(name: str, key: str) -> int:
    match = re.match(r"x(?P<x>-?\d+)_y(?P<y>-?\d+)", str(name))
    if not match:
        raise ValueError(f"Cannot read Nanophoton coordinate from column {name!r}.")
    return int(match.group(key))


def imaging_grid(wavenumber: np.ndarray, spectra: np.ndarray, coords: np.ndarray) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    validate_mapping(wavenumber, spectra)
    if not np.isfinite(coords).all():
        raise ValueError("Imaging coordinates must be finite.")
    x_vals = np.sort(np.unique(coords[:, 0]))
    y_vals = np.sort(np.unique(coords[:, 1]))
    pairs = set(map(tuple, coords.tolist()))
    if len(pairs) != len(coords):
        raise ValueError("Duplicate imaging coordinates found.")
    if len(pairs) != len(x_vals) * len(y_vals):
        raise ValueError("Incomplete imaging grid: some X/Y positions have no spectrum.")
    # All instruments use row-major [Y, X, wavenumber], independent of file order.
    data = np.empty((len(y_vals), len(x_vals), spectra.shape[1]), dtype=float)
    x_lookup = {v: i for i, v in enumerate(x_vals)}
    y_lookup = {v: i for i, v in enumerate(y_vals)}
    for coord, spectrum in zip(coords, spectra):
        data[y_lookup[coord[1]], x_lookup[coord[0]]] = spectrum
    return wavenumber, data, {"x": x_vals.tolist(), "y": y_vals.tolist()}


def read_imaging(content: bytes, instrument: str) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    if instrument == "Horiba":
        wavenumber, spectra, coords = read_horiba_table(content, 2)
        return imaging_grid(wavenumber, spectra, coords)

    if instrument == "Nanophoton":
        df = pd.read_csv(io.BytesIO(content), sep="\t")
        wavenumber = df["Wavenumber"].values.astype(float)
        cols = [c for c in df.columns if str(c).startswith("x")]
        if not cols:
            raise ValueError("No imaging coordinate columns found.")
        coords = np.asarray([(extract_xy(c, "x"), extract_xy(c, "y")) for c in cols], dtype=float)
        return imaging_grid(wavenumber, df[cols].values.astype(float).T, coords)

    raise ValueError(f"Unsupported imaging instrument: {instrument}")


def split_mapping_file(content: bytes, instrument: str, filename: str) -> bytes:
    files = []
    if instrument == "Horiba":
        stringio = io.StringIO(content.decode("utf-8-sig"))
        wavenumber = np.fromstring(stringio.readline(), sep="\t")
        remaining_data = np.loadtxt(stringio, delimiter="\t")
        spectra_data = np.atleast_2d(remaining_data)[:, 2:]
        files = [np.c_[wavenumber, spectrum] for spectrum in spectra_data]
    elif instrument == "Renishaw":
        df = pd.read_csv(io.BytesIO(content), delimiter="\t", header=None)
        ts = df.iloc[:, 0].values
        batch = np.unique(ts).shape[0]
        wave = df.iloc[:, 1].values.reshape(batch, -1)
        data = df.iloc[:, -1].values.reshape(batch, -1)
        files = [np.c_[wave[i], data[i]] for i in range(batch)]
    elif instrument == "Nanophoton":
        df = pd.read_csv(io.BytesIO(content), delimiter="\t")
        wavenumber = df["Wavenumber"].values
        spectra_cols = [col for col in df.columns if str(col).startswith("x")]
        spectra_data = df[spectra_cols].values
        files = [np.c_[wavenumber, spectra_data[:, i]] for i in range(spectra_data.shape[1])]
    else:
        raise ValueError(f"Unsupported instrument: {instrument}")
    if not files:
        raise ValueError("No spectra were found in the mapping file.")

    base = Path(filename or "mapping.txt").stem
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for i, arr in enumerate(files):
            arr_bytes = io.BytesIO()
            np.savetxt(arr_bytes, arr, delimiter="\t", fmt="%.4f")
            zip_file.writestr(f"{base}_split_{i + 1}.txt", arr_bytes.getvalue())
    return zip_buffer.getvalue()


def merge_spectrum_files(files: List[Tuple[str, bytes]]) -> bytes:
    mapping_data = []
    wavenumber = None
    for name, content in files:
        try:
            try:
                tmp = np.loadtxt(io.BytesIO(content), delimiter="\t")
            except ValueError:
                tmp = np.loadtxt(io.BytesIO(content), delimiter=",")
            tmp = np.atleast_2d(tmp)
            if tmp.shape[1] < 2:
                raise ValueError("expected at least two numeric columns")
            mapping_data.append(tmp[:, -1])
            if wavenumber is None:
                wavenumber = tmp[:, 0]
            elif len(wavenumber) != tmp.shape[0]:
                raise ValueError(f"{name} has a different spectral length.")
        except Exception as exc:
            raise ValueError(f"Error processing {name}: {exc}") from exc
    if wavenumber is None or not mapping_data:
        raise ValueError("Upload at least one spectrum file.")
    merged_array = np.vstack([wavenumber] + mapping_data)
    return pd.DataFrame(merged_array.T).to_csv(sep="\t", index=False, header=False, float_format="%.4f").encode("utf-8")


def horiba_to_nanophoton(content: bytes) -> bytes:
    stringio = io.StringIO(content.decode("utf-8-sig"))
    wavenumber = np.array([float(s) for s in stringio.readline().strip().split("\t") if s])
    remaining_data = np.loadtxt(stringio, delimiter="\t")
    remaining_data = np.atleast_2d(remaining_data)
    x_coords = remaining_data[:, 0]
    y_coords = remaining_data[:, 1]
    spectra = remaining_data[:, 2:]
    if wavenumber[0] > wavenumber[-1]:
        wavenumber = wavenumber[::-1]
        spectra = spectra[:, ::-1]
    x_unique = np.sort(np.unique(x_coords))
    y_unique = np.sort(np.unique(y_coords))
    x_index = np.searchsorted(x_unique, x_coords)
    y_index = np.searchsorted(y_unique, y_coords)
    order = np.lexsort((x_index, y_index))
    df = pd.DataFrame({"Wavenumber": wavenumber})
    for i in order:
        df[f"x{x_index[i]}_y{y_index[i]}"] = spectra[i, :]
    return df.to_csv(sep="\t", index=False, float_format="%.1f").encode("utf-8")


def nanophoton_to_horiba(content: bytes) -> bytes:
    imaging = pd.read_csv(io.BytesIO(content), delimiter="\t")
    wavenumber = imaging["Wavenumber"].values
    data_columns = [col for col in imaging.columns if str(col).startswith("x")]
    data = imaging[data_columns].values
    coords = pd.Series(data_columns).str.extract(r"x(\d+)_y(\d+)").astype(int)
    x_coords, y_coords = coords[0].values, coords[1].values
    if wavenumber[0] > wavenumber[-1]:
        wavenumber = wavenumber[::-1]
        data = data[::-1, :]
    x_unique = np.sort(np.unique(x_coords))
    y_unique = np.sort(np.unique(y_coords))
    x_index = np.searchsorted(x_unique, x_coords)
    y_index = np.searchsorted(y_unique, y_coords)
    order = np.lexsort((y_index, x_index))
    horiba_rows = []
    for idx in order:
        spectrum = data[:, idx]
        horiba_rows.append(np.concatenate([[x_index[idx], y_index[idx]], spectrum]))
    output = io.StringIO()
    output.write("\t\t" + "\t".join(map(str, wavenumber)) + "\n")
    np.savetxt(output, np.asarray(horiba_rows), fmt="%.1f", delimiter="\t")
    return output.getvalue().encode("utf-8")


def attachment_response(content: bytes, filename: str, media_type: str = "text/plain; charset=utf-8") -> Response:
    quoted = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename)
    return Response(content=content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{quoted}"'})


def denoise_spectrum(y: np.ndarray, params: Dict[str, Any], method: str) -> np.ndarray:
    return denoise(y, params, method)


def baseline_correct(y: np.ndarray, params: Dict[str, Any], method: str) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    return correct_baseline(y, params, method)


def denoise_matrix(matrix: np.ndarray, params: Dict[str, Any], method: str) -> np.ndarray:
    return denoise_batch(matrix, params, method)


def apply_pipeline(wavenumber: np.ndarray, data: np.ndarray, steps: List[Step]) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], List[Dict[str, Any]]]:
    if wavenumber.ndim != 1 or data.ndim not in (1, 2) or data.shape[-1] != len(wavenumber):
        raise ValueError('Spectral data must match the one-dimensional wavenumber axis')
    if not len(wavenumber) or not np.isfinite(wavenumber).all() or not np.isfinite(data).all():
        raise ValueError('Spectral values must be finite and non-empty')
    current_wn = wavenumber.copy()
    current = data.copy()
    baseline = None
    history: List[Dict[str, Any]] = []

    is_vector = current.ndim == 1
    if is_vector:
        current = current.reshape(1, -1)

    for step in steps:
        params = step.params or {}
        if step.type == "cut":
            start = float(params.get("start", current_wn.min()))
            end = float(params.get("end", current_wn.max()))
            if not np.isfinite([start, end]).all():
                raise ValueError('Cut boundaries must be finite')
            mask = (current_wn >= min(start, end)) & (current_wn <= max(start, end))
            if not mask.any():
                raise ValueError("Cut range does not overlap with the wavenumber axis.")
            current_wn = current_wn[mask]
            current = current[:, mask]
            if baseline is not None:
                baseline = baseline[:, mask]
            history.append({"type": "cut", "range": [min(start, end), max(start, end)]})
        elif step.type == "denoise":
            method = 'sg' if step.method == 'savitzky_golay' else step.method
            if method == 'tsvd' and is_vector:
                raise ValueError('TSVD requires a batch or hyperspectral dataset, not a single spectrum')
            params = validated_parameters(method, params)
            current = denoise_matrix(current, params, method)
            history.append({"type": "denoise", "method": method, "params": params})
        elif step.type == "baseline":
            params = validated_parameters(step.method, params)
            corrected = []
            baselines = []
            for row in current:
                row_corrected, row_baseline = baseline_correct(row, params, step.method)
                corrected.append(row_corrected)
                if row_baseline is not None:
                    baselines.append(row_baseline)
            current = np.vstack(corrected)
            if baselines:
                removed = np.vstack(baselines)
                baseline = removed if baseline is None else baseline + removed
            history.append({"type": "baseline", "method": step.method, "params": params})
        else:
            raise ValueError('Unknown pipeline step: ' + step.type)
        if not np.isfinite(current).all() or (baseline is not None and not np.isfinite(baseline).all()):
            raise ValueError('Algorithm produced non-finite values; adjust its parameters')

    return current_wn, current[0] if is_vector else current, (baseline[0] if is_vector and baseline is not None else baseline), history


def register_dataset(wavenumber: np.ndarray, data: np.ndarray, mode: str, filename: str, coordinates: Optional[Dict[str, Any]] = None) -> str:
    dataset_id = uuid.uuid4().hex
    dataset = {
        "wavenumber": np.asarray(wavenumber, dtype=float),
        "data": np.asarray(data, dtype=float),
        "mode": mode,
        "filename": filename,
        "coordinates": coordinates or {},
        "last_access": time.monotonic(),
    }
    purge_datasets()
    with DATASET_LOCK:
        if dataset['data'].nbytes > DATASET_MAX_BYTES:
            raise ValueError('Dataset exceeds the in-memory size limit')
        while DATASETS and sum(d['data'].nbytes for d in DATASETS.values()) + dataset['data'].nbytes > DATASET_MAX_BYTES:
            oldest = min(DATASETS, key=lambda key: DATASETS[key]['last_access'])
            del DATASETS[oldest]
        DATASETS[dataset_id] = dataset
    return dataset_id


def closest_wavenumber_index(wavenumber: np.ndarray, target: Optional[float] = None) -> int:
    if target is None:
        target = float((wavenumber.min() + wavenumber.max()) / 2)
    return int(np.abs(wavenumber - float(target)).argmin())


def rounded_list(data: np.ndarray, decimals: int = 5) -> List[Any]:
    return np.round(np.nan_to_num(data), decimals=decimals).tolist()


def cube_preview(data: np.ndarray, max_pixels: int = 60) -> Tuple[np.ndarray, int]:
    if data.ndim != 3:
        return data, 1
    height, width, _ = data.shape
    scale = max(1, int(np.ceil(max(height, width) / max_pixels)))
    return data[::scale, ::scale], scale


def heatmap_slice(wavenumber: np.ndarray, data: np.ndarray, target: Optional[float] = None) -> Tuple[np.ndarray, float, int, int]:
    idx = closest_wavenumber_index(wavenumber, target)
    if data.ndim == 3:
        preview, scale = cube_preview(data[:, :, idx])
        return preview, float(wavenumber[idx]), idx, scale
    return data, float(wavenumber[idx]), idx, 1


def mapping_payload(wavenumber: np.ndarray, data: np.ndarray, mode: str, filename: str, coordinates: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    dataset_id = register_dataset(wavenumber, data, mode, filename, coordinates)
    if data.ndim == 3:
        flat = data.reshape(-1, data.shape[-1])
        mean = flat.mean(axis=0)
    else:
        mean = data.mean(axis=0)
    preview, preview_wn, preview_idx, preview_scale = heatmap_slice(wavenumber, data)
    return {
        "dataset_id": dataset_id,
        "filename": filename,
        "mode": mode,
        "coordinates": coordinates or {},
        "wavenumber": wavenumber.tolist(),
        "shape": list(data.shape),
        "preview": rounded_list(preview),
        "preview_wavenumber": preview_wn,
        "preview_wavenumber_index": preview_idx,
        "preview_scale": preview_scale,
        "mean_spectrum": rounded_list(mean),
    }


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "code": 0,
        "msg": "RamanCloud preprocessing API is running",
        "data": {
            "framework": "FastAPI",
            "denoise": list(DENOISE_METHODS),
            "baseline": list(BASELINE_METHODS),
            "algorithm_version": "2.1.0",
            "dataset_idle_seconds": DATASET_TTL_SECONDS,
            "spectra_demos": list(DEMO_SPECTRA),
            "mapping_demos": list(DEMO_MAPPING),
        },
    }


@app.get("/api/demo/{name}")
def demo_spectrum(name: str) -> Dict[str, Any]:
    if name not in DEMO_SPECTRA:
        raise HTTPException(status_code=404, detail="Demo spectrum not found.")
    wave, intensity = read_spectrum((SAMPLES / DEMO_SPECTRA[name]).read_bytes())
    return {"code": 0, "msg": "Demo loaded", "data": {"name": name, "wavenumber": wave.tolist(), "intensity": intensity.tolist()}}


@app.post("/api/upload")
async def upload(files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    spectra = []
    for file in files:
        try:
            wave, intensity = read_spectrum(await file.read())
        except (ValueError, IndexError, pd.errors.ParserError) as exc:
            raise HTTPException(status_code=400, detail="{}: {}".format(file.filename, exc)) from exc
        spectra.append({"filename": file.filename, "wavenumber": wave.tolist(), "intensity": intensity.tolist(), "length": len(wave)})
    return {"code": 0, "msg": "Upload successful", "data": {"spectra": spectra}}


@app.get("/api/demo-hyperspectral/{name}")
def demo_mapping(name: str) -> Dict[str, Any]:
    if name not in DEMO_MAPPING:
        raise HTTPException(status_code=404, detail="Demo mapping not found.")
    sample, instrument, mode = DEMO_MAPPING[name]
    content = (SAMPLES / sample).read_bytes()
    if mode == "time_series":
        wave, data, coordinates = read_time_series(content, instrument)
    else:
        wave, data, coordinates = read_imaging(content, instrument)
    return {"code": 0, "msg": "Demo mapping loaded", "data": mapping_payload(wave, data, mode, sample, coordinates)}


@app.post("/api/upload-hyperspectral")
async def upload_mapping(
    file: UploadFile = File(...),
    instrument: str = Form("Horiba"),
    mode: str = Form("imaging"),
) -> Dict[str, Any]:
    content = await file.read()
    try:
        if mode == "time_series":
            wave, data, coordinates = read_time_series(content, instrument)
        elif mode == "imaging":
            wave, data, coordinates = read_imaging(content, instrument)
        else:
            raise ValueError("Unsupported mapping mode.")
    except (ValueError, KeyError, IndexError, pd.errors.ParserError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"code": 0, "msg": "Mapping uploaded", "data": mapping_payload(wave, data, mode, file.filename or "mapping.txt", coordinates)}


@app.post("/api/tools/split")
async def split_mapping_tool(file: UploadFile = File(...), instrument: str = Form("Horiba")) -> Response:
    try:
        content = split_mapping_file(await file.read(), instrument, file.filename or "mapping.txt")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return attachment_response(content, "split_files.zip", "application/zip")


@app.post("/api/tools/merge")
async def merge_files_tool(files: List[UploadFile] = File(...)) -> Response:
    try:
        payload = [(file.filename or f"spectrum_{idx + 1}.txt", await file.read()) for idx, file in enumerate(files)]
        content = merge_spectrum_files(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return attachment_response(content, "merged_mapping.txt")


@app.post("/api/tools/convert")
async def convert_mapping_tool(file: UploadFile = File(...), conversion: str = Form("horiba_to_nanophoton")) -> Response:
    try:
        content = await file.read()
        stem = Path(file.filename or "mapping.txt").stem
        if conversion == "horiba_to_nanophoton":
            converted = horiba_to_nanophoton(content)
            filename = f"{stem}_to_Nanophoton.txt"
        elif conversion == "nanophoton_to_horiba":
            converted = nanophoton_to_horiba(content)
            filename = f"{stem}_to_Horiba.txt"
        else:
            raise ValueError("Unsupported conversion.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return attachment_response(converted, filename)


@app.post("/api/process")
def process_spectrum(payload: SpectrumPayload) -> Dict[str, Any]:
    wave = clean_floats(payload.wavenumber)
    intensity = clean_floats(payload.intensity)
    out_wave, out_intensity, baseline, history = apply_pipeline(wave, intensity, payload.steps)
    return {
        "code": 0,
        "msg": "Pipeline completed",
        "data": {
            "wavenumber": out_wave.tolist(),
            "intensity": out_intensity.tolist(),
            "baseline": baseline.tolist() if baseline is not None else None,
            "history": history,
        },
    }


@app.post('/api/process-batch')
def process_batch(payload: BatchPayload):
    if not 1 <= len(payload.spectra) <= 100:
        raise ValueError('Batch processing accepts 1 to 100 spectra')
    results = []
    if any(step.method == 'tsvd' and step.type == 'denoise' for step in payload.steps):
        wave = clean_floats(payload.spectra[0].wavenumber)
        if any(not np.array_equal(wave, clean_floats(item.wavenumber)) for item in payload.spectra):
            raise ValueError('TSVD requires identical wavenumber axes across all spectra')
        matrix = clean_floats([item.intensity for item in payload.spectra])
        out_wave, out, baseline, history = apply_pipeline(wave, matrix, payload.steps)
        for index, item in enumerate(payload.spectra):
            results.append({'filename': item.filename, 'wavenumber': out_wave.tolist(),
                            'intensity': out[index].tolist(), 'history': history,
                            'baseline': baseline[index].tolist() if baseline is not None else None})
        return {'code': 0, 'msg': 'Batch pipeline completed', 'data': {'spectra': results}}
    for spectrum in payload.spectra:
        try:
            result = process_spectrum(SpectrumPayload(wavenumber=spectrum.wavenumber, intensity=spectrum.intensity, steps=payload.steps))['data']
        except ValueError as error:
            raise ValueError(spectrum.filename + ': ' + str(error))
        results.append(dict(result, filename=spectrum.filename))
    return {'code': 0, 'msg': 'Batch pipeline completed', 'data': {'spectra': results}}


@app.post("/api/process-hyperspectral")
def process_cube(payload: CubePayload) -> Dict[str, Any]:
    if payload.dataset_id:
        source = get_dataset(payload.dataset_id)
        wave = source["wavenumber"]
        source_data = source["data"]
        mode = source["mode"]
        filename = source["filename"]
        original_shape = source_data.shape
        coordinates = source.get("coordinates", {})
        spectra = source_data.reshape(-1, source_data.shape[-1]) if source_data.ndim == 3 else source_data
    else:
        wave = clean_floats(payload.wavenumber)
        spectra = clean_floats(payload.spectra)
        source_data = spectra
        mode = payload.mode
        filename = "processed_mapping.txt"
        original_shape = tuple(payload.shape or list(spectra.shape))
        coordinates = {}
        if spectra.ndim > 2:
            spectra = spectra.reshape(-1, spectra.shape[-1])
    out_wave, out_spectra, baseline, history = apply_pipeline(wave, spectra, payload.steps)
    mean = out_spectra.mean(axis=0)
    if mode == "imaging" and len(original_shape) >= 2:
        processed_cube = out_spectra.reshape(int(original_shape[0]), int(original_shape[1]), out_spectra.shape[-1])
    else:
        processed_cube = out_spectra
    processed_id = register_dataset(out_wave, processed_cube, mode, "processed_" + filename, coordinates)
    preview, preview_wn, preview_idx, preview_scale = heatmap_slice(out_wave, processed_cube)
    response = {
        "processed_dataset_id": processed_id,
        "coordinates": coordinates,
        "wavenumber": out_wave.tolist(),
        "preview": rounded_list(preview),
        "preview_wavenumber": preview_wn,
        "preview_wavenumber_index": preview_idx,
        "preview_scale": preview_scale,
        "mean_spectrum": rounded_list(mean),
        "shape": list(processed_cube.shape),
        "history": history,
    }
    if baseline is not None:
        response["baseline_mean"] = rounded_list(baseline.mean(axis=0))
        baseline_cube = baseline.reshape(processed_cube.shape)
        response['baseline_dataset_id'] = register_dataset(out_wave, baseline_cube, mode, 'baseline_' + filename, coordinates)
    return {"code": 0, "msg": "Mapping pipeline completed", "data": response}


@app.get("/api/hyperspectral-slice/{dataset_id}")
def get_hyperspectral_slice(dataset_id: str, wavenumber_value: Optional[float] = None) -> Dict[str, Any]:
    dataset = get_dataset(dataset_id)
    preview, preview_wn, preview_idx, preview_scale = heatmap_slice(dataset["wavenumber"], dataset["data"], wavenumber_value)
    return {
        "code": 0,
        "msg": "Slice loaded",
        "data": {
            "preview": rounded_list(preview),
            "wavenumber": preview_wn,
            "wavenumber_index": preview_idx,
            "preview_scale": preview_scale,
        },
    }


@app.get("/api/hyperspectral-pixel/{dataset_id}")
def get_hyperspectral_pixel(dataset_id: str, x: int = 0, y: int = 0) -> Dict[str, Any]:
    dataset = get_dataset(dataset_id)
    data = dataset["data"]
    if data.ndim != 3:
        raise HTTPException(status_code=400, detail="Pixel spectra are only available for imaging datasets.")
    row = int(max(0, min(y, data.shape[0] - 1)))
    col = int(max(0, min(x, data.shape[1] - 1)))
    return {
        "code": 0,
        "msg": "Pixel spectrum loaded",
        "data": {
            "x": col,
            "y": row,
            "coordinate_x": dataset["coordinates"].get("x", list(range(data.shape[1])))[col],
            "coordinate_y": dataset["coordinates"].get("y", list(range(data.shape[0])))[row],
            "wavenumber": dataset["wavenumber"].tolist(),
            "intensity": rounded_list(data[row, col]),
        },
    }


@app.get("/api/hyperspectral-spectrum/{dataset_id}")
def get_hyperspectral_spectrum(dataset_id: str, index: int = 0) -> Dict[str, Any]:
    dataset = get_dataset(dataset_id)
    data = dataset["data"]
    if data.ndim != 2:
        raise HTTPException(status_code=400, detail="Indexed spectra are only available for time-series datasets.")
    row = int(max(0, min(index, data.shape[0] - 1)))
    return {
        "code": 0,
        "msg": "Time-series spectrum loaded",
        "data": {
            "index": row,
            "time": dataset["coordinates"].get("time", list(range(data.shape[0])))[row],
            "wavenumber": dataset["wavenumber"].tolist(),
            "intensity": rounded_list(data[row]),
        },
    }


@app.post("/api/download")
def download(payload: DownloadPayload) -> Response:
    filename = payload.filename or "processed.txt"
    if payload.dataset_id is not None:
        dataset = get_dataset(payload.dataset_id)
        wave = dataset["wavenumber"]
        data = dataset["data"]
        spectra = data.reshape(-1, data.shape[-1]) if data.ndim == 3 else data
        matrix = np.vstack([wave, spectra]).T
        if payload.format == "mapping":
            coordinates = dataset.get("coordinates", {})
            if data.ndim == 3:
                xs = coordinates.get("x", list(range(data.shape[1])))
                ys = coordinates.get("y", list(range(data.shape[0])))
                positions = np.asarray([(x, y) for y in ys for x in xs])
                matrix = np.vstack([np.r_[np.nan, np.nan, wave], np.c_[positions, spectra]])
            else:
                times = coordinates.get("time", list(range(data.shape[0])))
                matrix = np.vstack([np.r_[np.nan, wave], np.c_[times, spectra]])
        content = pd.DataFrame(matrix).to_csv(sep="\t", index=False, header=False, float_format="%.17g" if payload.format == "mapping" else "%.8g")
    elif payload.spectra is not None:
        spectra = clean_floats(payload.spectra)
        wave = clean_floats(payload.wavenumber)
        matrix = np.vstack([wave, spectra]).T
        content = pd.DataFrame(matrix).to_csv(sep="\t", index=False, header=False, float_format="%.8g")
    else:
        wave = clean_floats(payload.wavenumber)
        intensity = clean_floats(payload.intensity)
        data = {"wavenumber": wave, "intensity": intensity}
        if payload.baseline is not None:
            data["baseline"] = clean_floats(payload.baseline)
        content = pd.DataFrame(data).to_csv(sep="\t", index=False, header=False, float_format="%.8g")
    quoted = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename)
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{quoted}"'},
    )


if __name__ == "__main__":
    import asyncio
    import uvicorn

    if not hasattr(asyncio, "current_task"):
        asyncio.current_task = asyncio.Task.current_task

    config = uvicorn.Config("app:app", host="127.0.0.1", port=5000, reload=False)
    server = uvicorn.Server(config)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(server.serve())
