# Local Setup

Run RamanCloud on your own computer with a Python backend and a browser-based frontend. No domain, certificate, or Nginx setup is needed for local use.

## Requirements

- Git
- Python 3.10 with pip and virtual environment support
- Node.js 22 or 24 with npm (frontend dependencies require Node.js 20 or newer)

The backend currently pins older versions of Pydantic and Uvicorn. Use Python 3.10 for this setup rather than assuming compatibility with newer Python versions.

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
python3.10 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

On Windows PowerShell, replace the virtual environment creation and activation commands with:

```powershell
py -3.10 -m venv venv
.\venv\Scripts\Activate.ps1
```

Keep this terminal open. The API listens on `http://127.0.0.1:5000`; its interactive documentation is at `http://127.0.0.1:5000/docs`.

## Start the Frontend

In a second terminal, from the repository root:

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --strictPort
```

Open **[http://localhost:5173/preprocessing/](http://localhost:5173/preprocessing/)**.

The frontend forwards `/preprocessing/api/` requests to the local backend. Both terminals must stay open while you use the app; press `Ctrl+C` in each to stop it.

## Try It

1. Open **Spectral Processing** and load a demo.
2. Add a denoising or baseline correction step and run the pipeline.
3. Compare the spectra and download the result.
4. Use **Hyperspectral Processing** to try time-series or imaging demos.

## Configuration and Troubleshooting

- **Port 5173 is occupied:** use `npm run dev -- --host 127.0.0.1 --port 5174 --strictPort` and open the same `/preprocessing/` path on port 5174.
- **Port 5000 is occupied:** choose a free backend port with `python -m uvicorn app:app --host 127.0.0.1 --port 5001` from the activated backend environment. Update the API proxy targets in `frontend/vite.config.js` to the same port, then restart Vite.
- **The page opens but data does not load:** check the backend terminal and open `http://127.0.0.1:5000/api/health` (or your chosen port). Confirm the Vite proxy uses that port.
- **Frontend installation fails:** check `node --version`, use a supported Node.js version, and run `npm ci` again.
- **Backend installation fails:** check the active Python version and install inside the virtual environment.

Keep the `/preprocessing/` base path for this setup. `npm run build` produces static files in `frontend/dist/`; serving those files separately also requires forwarding `/preprocessing/api/` to FastAPI. The repository's `scripts/deploy.sh`, service files, and certificate scripts are specific to the hosted installation and should not be run for local setup.
