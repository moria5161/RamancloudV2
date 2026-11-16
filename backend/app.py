"""
RamanCloud preprocessing API.

FastAPI service for spectrum, time-series, and hyperspectral Raman preprocessing.
The legacy Streamlit site runs independently in /media/ramancloud.
"""

import io
import os
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
if __package__:
    from .version import APPLICATION_VERSION
    from .web_security import WebSecurityMiddleware, current_owner, web_security_enabled, MAX_BODY_BYTES, MAX_NUMERIC_VALUES
    from .upload_archive import archive_uploads
    from .visit_statistics import router as visit_statistics_router
    from .structure_routes import router as structure_router
    from .algorithms.processing import denoise, denoise_batch, correct_baseline, correct_baseline_batch, validated_parameters, DENOISE_METHODS, BASELINE_METHODS
else:
    from version import APPLICATION_VERSION
    from web_security import WebSecurityMiddleware, current_owner, web_security_enabled, MAX_BODY_BYTES, MAX_NUMERIC_VALUES
    from upload_archive import archive_uploads
    from visit_statistics import router as visit_statistics_router
    from structure_routes import router as structure_router
    from algorithms.processing import denoise, denoise_batch, correct_baseline, correct_baseline_batch, validated_parameters, DENOISE_METHODS, BASELINE_METHODS


ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"

app = FastAPI(
    title="RamanCloud Preprocessing API",
    version=APPLICATION_VERSION,
    description="Cut, denoise, and baseline-correct Raman spectra and spectral cubes.",
    docs_url=None if web_security_enabled() else '/docs',
    redoc_url=None if web_security_enabled() else '/redoc',
    openapi_url=None if web_security_enabled() else '/openapi.json',
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get('RAMANCLOUD_WEB_ORIGINS', 'https://ramancloud.xmu.edu.cn,http://localhost:5173,http://127.0.0.1:5173').split(','),
    allow_credentials=True,
    allow_methods=['GET', 'POST', 'DELETE', 'OPTIONS'],
    allow_headers=['Content-Type', 'X-RamanCloud-CSRF', 'DNT', 'Sec-GPC'],
)
app.add_middleware(WebSecurityMiddleware)
app.include_router(visit_statistics_router)
app.include_router(structure_router)


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


class DownloadSpectrum(BaseModel):
    wavenumber: List[float]
    intensity: List[float]
    baseline: Optional[List[float]] = None


class BatchDownloadPayload(BaseModel):
    spectra: List[DownloadSpectrum] = Field(min_length=1, max_length=64)


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
BATCH_MAX_SPECTRA = 512
BATCH_CHUNK_SIZE = 64
DATASET_LOCK = RLock()
DATASET_TTL_SECONDS = 1800
DATASET_MAX_BYTES = 1024 * 1024 * 1024
DATASET_OWNER_MAX_BYTES = 512 * 1024 * 1024
DATASET_OWNER_MAX_COUNT = 64
DATASET_MAX_COUNT = 256


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
        if dataset_id not in DATASETS or DATASETS[dataset_id].get('owner') != current_owner():
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
        dataset = DATASETS.get(dataset_id)
        if current_owner() is not None and (dataset is None or dataset.get('owner') != current_owner()):
            raise HTTPException(404, 'Dataset not found or expired. Please reload your file.')
        DATASETS.pop(dataset_id, None)
    return {'code': 0, 'msg': 'Dataset released'}


def clean_floats(values: Any) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise ValueError("empty numeric array")
    if current_owner() is not None and arr.size > MAX_NUMERIC_VALUES:
        raise HTTPException(413, 'Numeric data exceeds the processing size limit')
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
    if current_owner() is not None and data.size > MAX_NUMERIC_VALUES:
        raise HTTPException(413, 'Mapping exceeds the processing size limit')
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
        if current_owner() is not None and df['time'].nunique() * df['wavenumber'].nunique() > MAX_NUMERIC_VALUES:
            raise HTTPException(413, 'Time-series grid exceeds the processing size limit')
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


def apply_pipeline(wavenumber: np.ndarray, data: np.ndarray, steps: List[Step], batch_size: Optional[int] = None) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], List[Dict[str, Any]]]:
    if current_owner() is not None and (data.size > MAX_NUMERIC_VALUES or len(steps) > 16):
        raise HTTPException(413, 'Pipeline exceeds the processing size or step limit')
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

    # F2P always resamples to 1600 points, including spectra shortened by a cut.
    f2p_steps = sum(step.type == 'denoise' and step.method == 'f2p' for step in steps)
    if current_owner() is not None and len(current) * 1600 * f2p_steps > MAX_NUMERIC_VALUES:
        raise HTTPException(413, 'F2P job exceeds the online inference size limit. Use fewer spectra or F2P steps.')

    for step in steps:
        params = step.params or {}
        if current_owner() is not None and step.type == 'denoise' and step.method == 'tsvd':
            rows, columns = current.shape
            if rows * columns * min(rows, columns) > 20_000_000_000:
                raise HTTPException(413, 'TSVD job is too large for online processing. Cut the spectral range or use local processing.')
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
            if batch_size and method != 'tsvd':
                current = np.vstack([denoise_matrix(current[offset:offset + batch_size], params, method)
                                     for offset in range(0, len(current), batch_size)])
            else:
                current = denoise_matrix(current, params, method)
            history.append({"type": "denoise", "method": method, "params": params})
        elif step.type == "baseline":
            params = validated_parameters(step.method, params)
            if batch_size:
                blocks = [correct_baseline_batch(current[offset:offset + batch_size], params, step.method)
                          for offset in range(0, len(current), batch_size)]
                current = np.vstack([block[0] for block in blocks])
                removed = None if blocks[0][1] is None else np.vstack([block[1] for block in blocks])
            else:
                current, removed = correct_baseline_batch(current, params, step.method)
            if removed is not None:
                baseline = removed if baseline is None else baseline + removed
            history.append({"type": "baseline", "method": step.method, "params": params})
        else:
            raise ValueError('Unknown pipeline step: ' + step.type)
        if not np.isfinite(current).all() or (baseline is not None and not np.isfinite(baseline).all()):
            raise ValueError('Algorithm produced non-finite values; adjust its parameters')

    return current_wn, current[0] if is_vector else current, (baseline[0] if is_vector and baseline is not None else baseline), history


def register_dataset(wavenumber: np.ndarray, data: np.ndarray, mode: str, filename: str, coordinates: Optional[Dict[str, Any]] = None) -> str:
    return register_datasets([(wavenumber, data, mode, filename, coordinates)])[0]


def register_datasets(entries):
    owner = current_owner()
    datasets = [{
        'wavenumber': np.asarray(wave, dtype=float), 'data': np.asarray(data, dtype=float),
        'mode': mode, 'filename': filename, 'coordinates': coordinates or {},
        'last_access': time.monotonic(), 'owner': owner,
    } for wave, data, mode, filename, coordinates in entries]
    size = lambda dataset: dataset['data'].nbytes + dataset['wavenumber'].nbytes
    incoming = sum(size(dataset) for dataset in datasets)
    purge_datasets()
    with DATASET_LOCK:
        own = [dataset for dataset in DATASETS.values() if dataset.get('owner') == owner]
        if owner is not None and (sum(size(dataset) for dataset in own) + incoming > DATASET_OWNER_MAX_BYTES
                                  or len(own) + len(datasets) > DATASET_OWNER_MAX_COUNT):
            raise HTTPException(413, 'Workspace storage limit reached. Clear unused data or load a smaller file.')
        if sum(size(dataset) for dataset in DATASETS.values()) + incoming > DATASET_MAX_BYTES or len(DATASETS) + len(datasets) > DATASET_MAX_COUNT:
            raise HTTPException(503, 'Dataset storage is busy. Please retry shortly.')
        identifiers = [uuid.uuid4().hex for _ in datasets]
        DATASETS.update(zip(identifiers, datasets))
    return identifiers


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
            "application_version": APPLICATION_VERSION,
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


async def read_upload(file: UploadFile) -> bytes:
    content = await file.read(MAX_BODY_BYTES + 1)
    if len(content) > MAX_BODY_BYTES:
        raise HTTPException(413, 'File exceeds the 200 MiB upload limit')
    return content


@app.post("/api/upload")
async def upload(files: List[UploadFile] = File(...), share_data: bool = Form(True)) -> Dict[str, Any]:
    if not 1 <= len(files) <= BATCH_MAX_SPECTRA:
        raise HTTPException(status_code=400, detail=f'Upload accepts 1 to {BATCH_MAX_SPECTRA} spectrum files')
    spectra = []
    originals = []
    for file in files:
        try:
            content = await read_upload(file)
            wave, intensity = await asyncio.to_thread(read_spectrum, content)
        except (ValueError, IndexError, pd.errors.ParserError) as exc:
            raise HTTPException(status_code=400, detail="{}: {}".format(file.filename, exc)) from exc
        spectra.append({"filename": file.filename, "wavenumber": wave.tolist(), "intensity": intensity.tolist(), "length": len(wave)})
        originals.append((file.filename or 'spectrum.txt', content))
    sharing = await asyncio.to_thread(archive_uploads, originals, 'web', 'spectrum', share_data=share_data)
    return {"code": 0, "msg": "Upload successful", "data": {"spectra": spectra}, "data_sharing": sharing}


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
    share_data: bool = Form(True),
) -> Dict[str, Any]:
    content = await read_upload(file)
    try:
        if mode == "time_series":
            wave, data, coordinates = await asyncio.to_thread(read_time_series, content, instrument)
        elif mode == "imaging":
            wave, data, coordinates = await asyncio.to_thread(read_imaging, content, instrument)
        else:
            raise ValueError("Unsupported mapping mode.")
    except (ValueError, KeyError, IndexError, pd.errors.ParserError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sharing = await asyncio.to_thread(archive_uploads, [(file.filename or 'mapping.txt', content)], 'web', mode, instrument, share_data)
    return {"code": 0, "msg": "Mapping uploaded", "data": mapping_payload(wave, data, mode, file.filename or "mapping.txt", coordinates), "data_sharing": sharing}


@app.post("/api/tools/split")
async def split_mapping_tool(file: UploadFile = File(...), instrument: str = Form("Horiba"), share_data: bool = Form(True)) -> Response:
    try:
        original = await read_upload(file)
        content = await asyncio.to_thread(split_mapping_file, original, instrument, file.filename or "mapping.txt")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sharing = await asyncio.to_thread(archive_uploads, [(file.filename or 'mapping.txt', original)], 'web', 'split', instrument, share_data)
    response = attachment_response(content, "split_files.zip", "application/zip")
    response.headers['X-RamanCloud-Data-Sharing'] = sharing['status']
    return response


@app.post("/api/tools/merge")
async def merge_files_tool(files: List[UploadFile] = File(...), share_data: bool = Form(True)) -> Response:
    if not 1 <= len(files) <= BATCH_MAX_SPECTRA:
        raise HTTPException(400, 'Too many files to merge')
    try:
        payload = [(file.filename or f"spectrum_{idx + 1}.txt", await read_upload(file)) for idx, file in enumerate(files)]
        content = await asyncio.to_thread(merge_spectrum_files, payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sharing = await asyncio.to_thread(archive_uploads, payload, 'web', 'merge', share_data=share_data)
    response = attachment_response(content, "merged_mapping.txt")
    response.headers['X-RamanCloud-Data-Sharing'] = sharing['status']
    return response


@app.post("/api/tools/convert")
async def convert_mapping_tool(file: UploadFile = File(...), conversion: str = Form("horiba_to_nanophoton"), share_data: bool = Form(True)) -> Response:
    try:
        content = await read_upload(file)
        stem = Path(file.filename or "mapping.txt").stem
        if conversion == "horiba_to_nanophoton":
            converted = await asyncio.to_thread(horiba_to_nanophoton, content)
            filename = f"{stem}_to_Nanophoton.txt"
        elif conversion == "nanophoton_to_horiba":
            converted = await asyncio.to_thread(nanophoton_to_horiba, content)
            filename = f"{stem}_to_Horiba.txt"
        else:
            raise ValueError("Unsupported conversion.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sharing = await asyncio.to_thread(archive_uploads, [(file.filename or 'mapping.txt', content)], 'web', 'convert', conversion, share_data)
    response = attachment_response(converted, filename)
    response.headers['X-RamanCloud-Data-Sharing'] = sharing['status']
    return response


@app.post("/api/process")
def process_spectrum(payload: SpectrumPayload) -> Dict[str, Any]:
    wave = clean_floats(payload.wavenumber)
    intensity = clean_floats(payload.intensity)
    out_wave, out_intensity, baseline, history = apply_pipeline(wave, intensity, payload.steps)
    return {
        "code": 0,
        "msg": "Pipeline completed",
        "data": {
            "application_version": APPLICATION_VERSION,
            "wavenumber": out_wave.tolist(),
            "intensity": out_intensity.tolist(),
            "baseline": baseline.tolist() if baseline is not None else None,
            "history": history,
        },
    }


@app.post('/api/process-batch')
def process_batch(payload: BatchPayload):
    if current_owner() is not None and sum(len(item.intensity) for item in payload.spectra) > MAX_NUMERIC_VALUES:
        raise HTTPException(413, 'Batch exceeds the processing size limit')
    if not 1 <= len(payload.spectra) <= BATCH_MAX_SPECTRA:
        raise ValueError(f'Batch processing accepts 1 to {BATCH_MAX_SPECTRA} spectra')
    results = []
    wave = clean_floats(payload.spectra[0].wavenumber)
    aligned = all(np.array_equal(wave, clean_floats(item.wavenumber)) for item in payload.spectra)
    joint = any(step.method == 'tsvd' and step.type == 'denoise' for step in payload.steps)
    if joint and not aligned:
        raise ValueError('TSVD requires identical wavenumber axes across all spectra')
    if aligned:
        matrix = clean_floats([item.intensity for item in payload.spectra])
        out_wave, out, baseline, history = apply_pipeline(wave, matrix, payload.steps, batch_size=BATCH_CHUNK_SIZE)
        for index, item in enumerate(payload.spectra):
            results.append({'application_version': APPLICATION_VERSION, 'filename': item.filename, 'wavenumber': out_wave.tolist(),
                            'intensity': out[index].tolist(), 'history': history,
                            'baseline': baseline[index].tolist() if baseline is not None else None})
        return {'code': 0, 'msg': 'Batch pipeline completed', 'data': {'spectra': results}}
    for offset in range(0, len(payload.spectra), BATCH_CHUNK_SIZE):
        for spectrum in payload.spectra[offset:offset + BATCH_CHUNK_SIZE]:
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
    entries = [(out_wave, processed_cube, mode, 'processed_' + filename, coordinates)]
    if baseline is not None:
        entries.append((out_wave, baseline.reshape(processed_cube.shape), mode, 'baseline_' + filename, coordinates))
    identifiers = register_datasets(entries)
    processed_id = identifiers[0]
    preview, preview_wn, preview_idx, preview_scale = heatmap_slice(out_wave, processed_cube)
    response = {
        "application_version": APPLICATION_VERSION,
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
        response['baseline_dataset_id'] = identifiers[1]
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


def spectrum_download_text(wavenumber, intensity, baseline=None):
    data = {"wavenumber": clean_floats(wavenumber), "intensity": clean_floats(intensity)}
    if baseline is not None:
        data["baseline"] = clean_floats(baseline)
    return pd.DataFrame(data).to_csv(sep="\t", index=False, header=False, float_format="%.8g")


@app.post("/api/download-batch")
def download_batch(payload: BatchDownloadPayload):
    count = sum(len(item.wavenumber) + len(item.intensity) + len(item.baseline or [])
                for item in payload.spectra)
    if count > MAX_NUMERIC_VALUES:
        raise HTTPException(413, 'Batch download exceeds the numeric data size limit')
    spectra = []
    for item in payload.spectra:
        spectra.append({
            "content": spectrum_download_text(item.wavenumber, item.intensity),
            "baseline": spectrum_download_text(item.wavenumber, item.baseline) if item.baseline is not None else None,
        })
    return {"code": 0, "data": {"spectra": spectra}}


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
        content = spectrum_download_text(payload.wavenumber, payload.intensity, payload.baseline)
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

    config = uvicorn.Config("app:app", host="127.0.0.1", port=5000, reload=False,
                            limit_concurrency=64, backlog=128, timeout_keep_alive=5,
                            timeout_graceful_shutdown=60, forwarded_allow_ips='127.0.0.1')
    server = uvicorn.Server(config)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(server.serve())
