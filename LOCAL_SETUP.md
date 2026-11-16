# Local Setup

Run RamanCloud on your own computer with a Python backend and a browser-based frontend. No domain, certificate, or Nginx setup is needed for local use.

## Requirements

- Git
- Python 3.11 with pip and virtual environment support
- Node.js 22.12+ or 24 with npm

Python 3.11 is the tested runtime. Baseline correction uses pybaselines 1.2.1.

## Get the Code

```bash
git clone https://github.com/moria5161/RamancloudV2.git
cd RamancloudV2
```

The repository includes demo datasets under `backend/samples/`.

## Start the Backend

In your first terminal, from the repository root:

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

On Windows PowerShell, replace the virtual environment creation and activation commands with:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Keep this terminal open. The API listens on `http://127.0.0.1:5000`; its interactive documentation is at `http://127.0.0.1:5000/docs`.

## Optional Pretrained Models

The current model definitions and full inference pipelines are included in this
checkout. The weights are provided separately by their owner; the source-code
license does not grant redistribution rights for weights. Do not commit them.

For F2P and AirNet on Linux or Windows, install the tested CPU runtime in the
activated backend virtual environment:

```bash
python -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
```

On Apple Silicon macOS, use `python -m pip install torch==2.5.1` from PyPI instead.

AirNet needs PyTorch and the pretrained model weights; the weights are not
included in Git or the Python package. Install `torch>=2.5,<3` in the backend
environment and place the AirNet state dictionary at
`backend/algorithms/baseline_cor/models/airnet.pth`,
or set `RAMANCLOUD_AIRNET_MODEL` to its absolute path before starting the backend.
Without these, other algorithms remain available and AirNet returns an explicit
configuration error. The hosted website has the model configured.

F2P uses the same PyTorch dependency. Place its inference-only state dictionary
at `backend/algorithms/denoising/f2p/models/f2p_rpe_best.pth`, or set
`RAMANCLOUD_F2P_MODEL` to an absolute path. Its network configuration is in
`backend/algorithms/denoising/f2p/config.json`. Only inference is included;
training datasets, random masking, optimizers, and training schedulers are not
needed. Both hosted models run on CPU with bounded inference batches.

The current F2P class is `Fast2PeakRPE`. The old `SpecTransformer` and
`F2P_ps16_dp8_mr0.25.pth` are incompatible with this version. Do not bypass
state-dictionary mismatches with `strict=False`.

With the virtual environment still activated, run from the repository root:

```bash
python scripts/verify_private_models.py --output model-demo-results.txt
```

This loads both models strictly, processes the included 1600-point demo with
the website's normalization/resampling and output restoration, and checks
finite, repeatable output. The text output contains the input spectrum and
both processed spectra. This checks installation and inference, not scientific
accuracy against ground truth. Successful output names `Fast2PeakRPE` (110
state entries) and `ResUNet_2500` (233 state entries).

Environment-variable alternatives (use absolute paths to your private files):

```bash
export RAMANCLOUD_F2P_MODEL=/private/path/f2p_rpe_best.pth
export RAMANCLOUD_AIRNET_MODEL=/private/path/airnet.pth
```

```powershell
$env:RAMANCLOUD_F2P_MODEL = "C:\private\f2p_rpe_best.pth"
$env:RAMANCLOUD_AIRNET_MODEL = "C:\private\airnet.pth"
```

Structure-to-spectrum prediction has separate optional dependencies. With CPU
PyTorch 2.5.1 installed, run `python -m pip install -r requirements-structure.txt`
from the activated backend directory. Place the three private model state
dictionaries listed in `backend/algorithms/structure_spectrum/README.md` in that
module's `models/` directory. These weights are not included in Git. Without
them, spectral preprocessing still works; molecular prediction reports that
the models are unavailable. The browser-based molecular editor is included in
the frontend build and requires no external service.

On minimal Debian/Ubuntu Linux installations, Open Babel's XYZ reader also
needs the system library `libXrender.so.1`. Install it with
`sudo apt-get install libxrender1` before using molecular prediction. An Open
Babel plugin error mentioning this library is a native dependency issue, not
a missing model weight. F2P and AirNet do not need Open Babel or this library.

Alternatively, set `RAMANCLOUD_STRUCTURE_MODEL_DIR` to a private directory
containing all three files. Run the following from the repository root to
verify a benzene prediction as well:

```bash
python scripts/verify_private_models.py --structure
```
The complete molecular dependency stack is tested on Linux x86-64 with Python
3.11 and CPU PyTorch 2.5.1; its compiled PyG wheels are platform-specific.
The two F2P/AirNet weights alone do not enable molecular spectrum prediction.

For the optional Python/MCP package, install from the repository root with
`python -m pip install '.[mcp]'` after installing CPU PyTorch as above. Use the
environment-variable paths for private weights, then run
`python scripts/verify_private_models.py --installed`. Model source, F2P
configuration, and molecular examples are packaged; weights are not.

## Start the Frontend

In a second terminal, from the repository root:

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --strictPort
```

Open **[http://localhost:5173/](http://localhost:5173/)**.

The frontend forwards `/ramancloud-api/` requests to the local backend's `/api/` routes. Both terminals must stay open while you use the app; press `Ctrl+C` in each to stop it.

## Try It

1. Open **Spectral Processing** and load a demo.
2. Add a denoising or baseline correction step and run the pipeline.
3. Compare the spectra and download the result.
4. Use **Hyperspectral Processing** to try time-series or imaging demos.

Single-spectrum uploads accept up to 512 files. Independent pipelines process
sequential groups of up to 64, preserving file order. TSVD uses the entire
aligned batch for its joint decomposition; independent steps around it still
run in groups of up to 64. Batch downloads include every processed spectrum.

## Configuration and Troubleshooting

Original-file archiving is disabled in a fresh local installation. To enable it
on a hosted service, set `RAMANCLOUD_UPLOAD_ARCHIVE_DIR` to a private absolute
directory outside the web root. Original bytes are stored in that directory;
`uploads.sqlite3` indexes their filenames, source, module, SHA-256, and UTC time.
SQLite is included with Python; no separate database server is needed.
The hosted website's Settings checkbox is on by default, and uploads explicitly
send `share_data=true` or `false`. Turning sharing off affects future uploads,
not earlier contributions. Demo selections and processing results are never
archived. Update user-facing retention notices if you change this policy.
Requests without `share_data` do not archive originals, protecting cached older
clients that have not yet displayed the sharing notice.
`RAMANCLOUD_UPLOAD_ARCHIVE_DISABLED=1` disables archiving regardless of configuration.
The optional, untracked `backend/runtime/upload-archive.json` can configure
`directory`, `max_file_bytes` (default 200 MiB), and `max_total_bytes` (default
20 GiB of indexed uploads). Back up the entire directory, including the SQLite
index and original files; never expose it through the web server or commit it.

- **Port 5173 is occupied:** use `npm run dev -- --host 127.0.0.1 --port 5174 --strictPort` and open `http://localhost:5174/`.
- **Port 5000 is occupied:** choose a free backend port with `python -m uvicorn app:app --host 127.0.0.1 --port 5001` from the activated backend environment. Update the API proxy targets in `frontend/vite.config.js` to the same port, then restart Vite.
- **The page opens but data does not load:** check the backend terminal and open `http://127.0.0.1:5000/api/health` (or your chosen port). Confirm the Vite proxy uses that port.
- **Local Python/MCP requests time out when a proxy is configured:** include `127.0.0.1,localhost,::1` in `NO_PROXY` so loopback requests stay local.
- **Frontend installation fails:** check `node --version`, use a supported Node.js version, and run `npm ci` again.
- **Backend installation fails:** check the active Python version and install inside the virtual environment.

`npm run build` produces static files in `frontend/dist/` for the site root. A separate web server must serve frontend routes with an `index.html` fallback and forward `/ramancloud-api/` to FastAPI's `/api/`. This dedicated prefix avoids conflicts with other applications using `/api/` on the same host. Set `VITE_API_BASE` before building only if your gateway uses a different API prefix; when web session security is enabled, also align `RAMANCLOUD_SESSION_COOKIE_PATH` with that prefix. The repository's `scripts/deploy.sh`, service files, and certificate scripts are specific to the hosted installation and should not be run for local setup.
