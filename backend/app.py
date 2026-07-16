"""
RamanCloud preprocessing API.

FastAPI service for spectrum, time-series, and hyperspectral Raman preprocessing.
The original Streamlit site remains untouched in /media/ramancloud.
"""

import io
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pywt
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from scipy import sparse
from scipy.signal import savgol_filter
from scipy.sparse.linalg import spsolve


ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"

app = FastAPI(
    title="RamanCloud Preprocessing API",
    version="2.0.0",
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


class DownloadPayload(BaseModel):
    wavenumber: List[float]
    intensity: Optional[List[float]] = None
    spectra: Optional[Any] = None
    dataset_id: Optional[str] = None
    shape: Optional[List[int]] = None
    mode: str = "spectrum"
    baseline: Optional[List[float]] = None
    filename: str = "processed.txt"


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


def clean_floats(values: Any) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise ValueError("empty numeric array")
    return np.nan_to_num(arr, copy=False)


def read_spectrum(content: bytes) -> Tuple[np.ndarray, np.ndarray]:
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
        return df.iloc[:, -2].values.astype(float), df.iloc[:, -1].values.astype(float)
    return df.iloc[:, 0].values.astype(float), df.iloc[:, -1].values.astype(float)


def read_time_series(content: bytes, instrument: str) -> Tuple[np.ndarray, np.ndarray, List[Any]]:
    if instrument == "Horiba":
        df = pd.read_csv(io.BytesIO(content), sep="\t", header=None)
        wavenumber = df.iloc[0].dropna().values.astype(float)
        data = df.iloc[1:, 1 : len(wavenumber) + 1].values.astype(float)
        index = list(range(data.shape[0]))
        return wavenumber, data, index

    if instrument == "Renishaw":
        df = pd.read_csv(io.BytesIO(content), sep="\t", header=None)
        if df.shape[1] < 3:
            raise ValueError("Renishaw time series requires time, wavenumber, intensity columns.")
        df = df.iloc[:, :3]
        df.columns = ["time", "wavenumber", "intensity"]
        pivot = df.pivot_table(index="time", columns="wavenumber", values="intensity", aggfunc="first")
        return pivot.columns.values.astype(float), pivot.values.astype(float), pivot.index.tolist()

    if instrument == "Nanophoton":
        df = pd.read_csv(io.BytesIO(content), sep="\t")
        wavenumber = df.iloc[:, 0].values.astype(float)
        data_cols = np.arange(1, df.shape[1], 2)
        data = df.iloc[:, data_cols].values.astype(float).T[::-1]
        return wavenumber, data, list(range(data.shape[0]))

    raise ValueError(f"Unsupported instrument: {instrument}")


def extract_xy(name: str, key: str) -> int:
    match = re.match(r"x(?P<x>\d+)_y(?P<y>\d+)", str(name))
    if not match:
        raise ValueError(f"Cannot read Nanophoton coordinate from column {name!r}.")
    return int(match.group(key))


def read_imaging(content: bytes, instrument: str) -> Tuple[np.ndarray, np.ndarray, List[Any]]:
    if instrument == "Horiba":
        df = pd.read_csv(io.BytesIO(content), sep="\t", header=None)
        wavenumber = df.iloc[0].dropna().values.astype(float)
        coords = df.iloc[1:, :2].values.astype(float)
        spectra = df.iloc[1:, 2 : len(wavenumber) + 2].values.astype(float)
        x_vals = np.sort(np.unique(coords[:, 0]))
        y_vals = np.sort(np.unique(coords[:, 1]))
        data = np.zeros((len(x_vals), len(y_vals), spectra.shape[1]), dtype=float)
        x_lookup = {v: i for i, v in enumerate(x_vals)}
        y_lookup = {v: i for i, v in enumerate(y_vals)}
        for coord, spectrum in zip(coords, spectra):
            data[x_lookup[coord[0]], y_lookup[coord[1]]] = spectrum
        return wavenumber, data, coords.tolist()

    if instrument == "Nanophoton":
        df = pd.read_csv(io.BytesIO(content), sep="\t")
        wavenumber = df["Wavenumber"].values.astype(float)
        cols = [c for c in df.columns if str(c).startswith("x")]
        x_size = max(extract_xy(c, "x") for c in cols) + 1
        y_size = max(extract_xy(c, "y") for c in cols) + 1
        data = np.zeros((y_size, x_size, len(wavenumber)), dtype=float)
        for col in cols:
            x, y = extract_xy(col, "x"), extract_xy(col, "y")
            data[y, x] = df[col].values.astype(float)
        return wavenumber, data, [(extract_xy(c, "x"), extract_xy(c, "y")) for c in cols]

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


def normalize_window(window: int, order: int, length: int) -> int:
    window = max(3, int(window))
    if window % 2 == 0:
        window += 1
    if window >= length:
        window = length - 1 if (length - 1) % 2 else length - 2
    if window <= order:
        window = order + 2 + ((order + 2) % 2 == 0)
    if window >= length:
        raise ValueError("Savitzky-Golay window is too large for the selected range.")
    return window


def denoise_spectrum(y: np.ndarray, params: Dict[str, Any], method: str) -> np.ndarray:
    if method in ("skip", "", None):
        return y.copy()
    if method in ("sg", "savitzky_golay"):
        order = int(params.get("order", 3))
        window = normalize_window(int(params.get("window_size", 7)), order, len(y))
        return savgol_filter(y, window, order)
    if method == "wtd":
        wavelet = params.get("wavelet", "db3")
        level = int(params.get("level", 3))
        max_level = pywt.dwt_max_level(len(y), pywt.Wavelet(wavelet).dec_len)
        level = max(1, min(level, max_level))
        coeffs = pywt.wavedec(y, wavelet, level=level)
        sigma = np.median(np.abs(coeffs[-1])) / 0.6745 if len(coeffs[-1]) else 0
        threshold = 0.8 * np.sqrt(2 * np.log(max(len(y), 2))) * sigma
        coeffs = [c if i == 0 else pywt.threshold(c, threshold, mode="soft") for i, c in enumerate(coeffs)]
        return pywt.waverec(coeffs, wavelet)[: len(y)]
    if method == "tsvd":
        matrix = y.reshape(1, -1)
        return denoise_matrix(matrix, params, method)[0]
    if method == "peer":
        loops = int(params.get("loops", 3))
        window = normalize_window(2 * int(params.get("half_k_threshold", 2)) + 3, 2, len(y))
        out = y.copy()
        for _ in range(max(1, loops)):
            smooth = savgol_filter(out, window, 2)
            residual = out - smooth
            keep = np.abs(residual) > np.percentile(np.abs(residual), 85)
            out = np.where(keep, out, smooth)
        return out
    raise ValueError(f"Unknown denoise method: {method}")


def whittaker_baseline(y: np.ndarray, lam: float = 1e7, diff_order: int = 2, p: float = 0.01, niter: int = 15) -> np.ndarray:
    length = len(y)
    diff_order = max(1, min(int(diff_order), 3))
    dmat = sparse.eye(length, format="csc")
    for _ in range(diff_order):
        dmat = dmat[1:] - dmat[:-1]
    weights = np.ones(length)
    for _ in range(max(1, int(niter))):
        wmat = sparse.diags(weights, 0, shape=(length, length), format="csc")
        baseline = spsolve(wmat + float(lam) * (dmat.T @ dmat), weights * y)
        weights = p * (y > baseline) + (1 - p) * (y <= baseline)
    return baseline


def rolling_min_baseline(y: np.ndarray, half_window: int = 40) -> np.ndarray:
    half = max(2, int(half_window))
    series = pd.Series(y)
    base = series.rolling(2 * half + 1, center=True, min_periods=1).min()
    base = base.rolling(2 * half + 1, center=True, min_periods=1).mean()
    return base.values.astype(float)


def polynomial_baseline(y: np.ndarray, order: int = 3, quantile: float = 0.35) -> np.ndarray:
    x = np.linspace(-1, 1, len(y))
    mask = np.ones(len(y), dtype=bool)
    order = max(1, min(int(order), 5))
    for _ in range(8):
        coeff = np.polyfit(x[mask], y[mask], order)
        base = np.polyval(coeff, x)
        residual = y - base
        mask = residual <= np.quantile(residual, quantile)
        if mask.sum() <= order + 1:
            break
    return base


def baseline_correct(y: np.ndarray, params: Dict[str, Any], method: str) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    if method in ("skip", "", None):
        return y.copy(), None
    if method in ("airpls", "aspls", "aabs", "irsqr"):
        lam = float(params.get("lam", params.get("lambda_", 1e7)))
        order = int(params.get("diff_order", params.get("order_", 2)))
        p = float(params.get("quantile", 0.01))
        baseline = whittaker_baseline(y, lam=lam, diff_order=order, p=max(0.001, min(p, 0.49)))
    elif method in ("imodpoly", "penalizedpoly", "airpls_old"):
        baseline = polynomial_baseline(y, int(params.get("poly_order", params.get("order_", 3))))
    elif method in ("rollingball", "mormol", "snip"):
        baseline = rolling_min_baseline(y, int(params.get("half_window", params.get("max_half_window", 40))))
    else:
        raise ValueError(f"Unknown baseline method: {method}")
    return y - baseline, baseline


def denoise_matrix(matrix: np.ndarray, params: Dict[str, Any], method: str) -> np.ndarray:
    if method == "tsvd":
        threshold = float(params.get("threshold", 1e-3))
        u, s, vh = np.linalg.svd(matrix, full_matrices=False)
        keep = max(1, int(np.sum((s / max(s[0], 1e-12)) > threshold)))
        return (u[:, :keep] * s[:keep]) @ vh[:keep]
    return np.vstack([denoise_spectrum(row, params, method) for row in matrix])


def apply_pipeline(wavenumber: np.ndarray, data: np.ndarray, steps: List[Step]) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], List[Dict[str, Any]]]:
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
            mask = (current_wn >= min(start, end)) & (current_wn <= max(start, end))
            if not mask.any():
                raise ValueError("Cut range does not overlap with the wavenumber axis.")
            current_wn = current_wn[mask]
            current = current[:, mask]
            history.append({"type": "cut", "range": [min(start, end), max(start, end)]})
        elif step.type == "denoise":
            current = denoise_matrix(current, params, step.method)
            history.append({"type": "denoise", "method": step.method, "params": params})
        elif step.type == "baseline":
            corrected = []
            baselines = []
            for row in current:
                row_corrected, row_baseline = baseline_correct(row, params, step.method)
                corrected.append(row_corrected)
                if row_baseline is not None:
                    baselines.append(row_baseline)
            current = np.vstack(corrected)
            baseline = np.vstack(baselines) if baselines else None
            history.append({"type": "baseline", "method": step.method, "params": params})

    return current_wn, current[0] if is_vector else current, (baseline[0] if is_vector and baseline is not None else baseline), history


def register_dataset(wavenumber: np.ndarray, data: np.ndarray, mode: str, filename: str) -> str:
    dataset_id = uuid.uuid4().hex
    DATASETS[dataset_id] = {
        "wavenumber": np.asarray(wavenumber, dtype=float),
        "data": np.asarray(data, dtype=float),
        "mode": mode,
        "filename": filename,
    }
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


def mapping_payload(wavenumber: np.ndarray, data: np.ndarray, mode: str, filename: str) -> Dict[str, Any]:
    dataset_id = register_dataset(wavenumber, data, mode, filename)
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
            "denoise": ["sg", "wtd", "peer", "tsvd", "skip"],
            "baseline": ["airpls", "aspls", "aabs", "imodpoly", "penalizedpoly", "rollingball", "mormol", "snip", "irsqr", "skip"],
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
        wave, intensity = read_spectrum(await file.read())
        spectra.append({"filename": file.filename, "wavenumber": wave.tolist(), "intensity": intensity.tolist(), "length": len(wave)})
    return {"code": 0, "msg": "Upload successful", "data": {"spectra": spectra}}


@app.get("/api/demo-hyperspectral/{name}")
def demo_mapping(name: str) -> Dict[str, Any]:
    if name not in DEMO_MAPPING:
        raise HTTPException(status_code=404, detail="Demo mapping not found.")
    sample, instrument, mode = DEMO_MAPPING[name]
    content = (SAMPLES / sample).read_bytes()
    if mode == "time_series":
        wave, data, _ = read_time_series(content, instrument)
    else:
        wave, data, _ = read_imaging(content, instrument)
    return {"code": 0, "msg": "Demo mapping loaded", "data": mapping_payload(wave, data, mode, sample)}


@app.post("/api/upload-hyperspectral")
async def upload_mapping(
    file: UploadFile = File(...),
    instrument: str = Form("Horiba"),
    mode: str = Form("imaging"),
) -> Dict[str, Any]:
    content = await file.read()
    if mode == "time_series":
        wave, data, _ = read_time_series(content, instrument)
    else:
        wave, data, _ = read_imaging(content, instrument)
    return {"code": 0, "msg": "Mapping uploaded", "data": mapping_payload(wave, data, mode, file.filename or "mapping.txt")}


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


@app.post("/api/process-hyperspectral")
def process_cube(payload: CubePayload) -> Dict[str, Any]:
    if payload.dataset_id:
        if payload.dataset_id not in DATASETS:
            raise HTTPException(status_code=404, detail="Dataset not found or expired.")
        source = DATASETS[payload.dataset_id]
        wave = source["wavenumber"]
        source_data = source["data"]
        mode = source["mode"]
        filename = source["filename"]
        original_shape = source_data.shape
        spectra = source_data.reshape(-1, source_data.shape[-1]) if source_data.ndim == 3 else source_data
    else:
        wave = clean_floats(payload.wavenumber)
        spectra = clean_floats(payload.spectra)
        source_data = spectra
        mode = payload.mode
        filename = "processed_mapping.txt"
        original_shape = tuple(payload.shape or list(spectra.shape))
        if spectra.ndim > 2:
            spectra = spectra.reshape(-1, spectra.shape[-1])
    out_wave, out_spectra, baseline, history = apply_pipeline(wave, spectra, payload.steps)
    mean = out_spectra.mean(axis=0)
    if mode == "imaging" and len(original_shape) >= 2:
        processed_cube = out_spectra.reshape(int(original_shape[0]), int(original_shape[1]), out_spectra.shape[-1])
    else:
        processed_cube = out_spectra
    processed_id = register_dataset(out_wave, processed_cube, mode, "processed_" + filename)
    preview, preview_wn, preview_idx, preview_scale = heatmap_slice(out_wave, processed_cube)
    response = {
        "processed_dataset_id": processed_id,
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
    return {"code": 0, "msg": "Mapping pipeline completed", "data": response}


@app.get("/api/hyperspectral-slice/{dataset_id}")
def get_hyperspectral_slice(dataset_id: str, wavenumber_value: Optional[float] = None) -> Dict[str, Any]:
    if dataset_id not in DATASETS:
        raise HTTPException(status_code=404, detail="Dataset not found or expired.")
    dataset = DATASETS[dataset_id]
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
    if dataset_id not in DATASETS:
        raise HTTPException(status_code=404, detail="Dataset not found or expired.")
    dataset = DATASETS[dataset_id]
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
            "wavenumber": dataset["wavenumber"].tolist(),
            "intensity": rounded_list(data[row, col]),
        },
    }


@app.post("/api/download")
def download(payload: DownloadPayload) -> Response:
    filename = payload.filename or "processed.txt"
    if payload.dataset_id is not None:
        if payload.dataset_id not in DATASETS:
            raise HTTPException(status_code=404, detail="Dataset not found or expired.")
        dataset = DATASETS[payload.dataset_id]
        wave = dataset["wavenumber"]
        data = dataset["data"]
        spectra = data.reshape(-1, data.shape[-1]) if data.ndim == 3 else data
        matrix = np.vstack([wave, spectra]).T
        content = pd.DataFrame(matrix).to_csv(sep="\t", index=False, header=False, float_format="%.8g")
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

    config = uvicorn.Config("app:app", host="0.0.0.0", port=5000, reload=False)
    server = uvicorn.Server(config)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(server.serve())
