# RamanCloud Desktop

The desktop app runs the existing React frontend and packaged FastAPI backend on
a private `127.0.0.1` socket in one process. It uses pywebview with the OS WebView,
not Electron, Qt, or a bundled Chromium browser. No Python or Node installation is
needed to run a release download. The `/preprocessing/` UI and original API paths
are retained, including all workspaces, tools, settings, tutorials, research
images, and local globe geometry.

## Release Downloads

Tag `desktop-v2.2.0` (and subsequent `desktop-v*` tags) triggers
`.github/workflows/desktop-release.yml`. Download the matching ZIP from the
repository's GitHub Releases:

| Asset | System | Launch |
| --- | --- | --- |
| `RamanCloud-2.2.0-windows-x64.zip` | Windows x64 | Extract the whole folder; open `RamanCloud.exe` |
| `RamanCloud-2.2.0-macos-x64.zip` | Intel Mac | Extract; move `RamanCloud.app` to Applications |
| `RamanCloud-2.2.0-macos-arm64.zip` | Apple Silicon Mac | Extract; move `RamanCloud.app` to Applications |

Keep every file in the Windows onedir folder. The `.app` contains the entire Mac
bundle. Individual `.sha256` files and `SHA256SUMS.txt` accompany the assets.
Use `Get-FileHash <archive> -Algorithm SHA256` on Windows or
`shasum -a 256 <archive>` on macOS to compare checksums.

Windows requires .NET Framework 4.6.2+ and **Microsoft Edge WebView2 Runtime**.
The installed Microsoft Edge browser is not a substitute for that runtime.
Most current Windows machines already have it. For air-gapped machines that do
not, supply Microsoft's **x64 Evergreen Standalone Installer**, install it once,
then launch RamanCloud. RamanCloud never downloads a runtime at startup. See
[Microsoft's offline deployment instructions](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution#offline-deployment).
macOS uses the system WKWebView; no separate browser runtime is needed.
[pywebview's engine requirements](https://pywebview.flowrl.com/guide/web_engine.html)
describe the native providers.

Mac builds are separate native architectures, built on macOS 15. The workflow
does not promise compatibility with older macOS versions. Without a configured
Developer ID identity, PyInstaller applies ad-hoc signing; releases are **not
Apple-notarized** and Gatekeeper may require explicit approval under Privacy &
Security. Windows releases are not Authenticode-signed by this workflow. Do not
disable OS security globally to run an unsigned application.

## Build Locally

Build on the target OS and architecture using Python 3.11 and Node 22. The
root package exposes `ramancloud_backend`, includes its sample TXT files and
`historical_visits.json`, and registers `ramancloud-desktop = desktop.launcher:main`.

```bash
cd frontend
npm ci
npm run build
cd ..
python -m pip install '.[desktop,dev]' -r desktop/requirements-build.txt
python -m unittest discover -s desktop/tests -v
python -m desktop --smoke-test
python desktop/build.py
python desktop/verify_bundle.py --mode api
python desktop/verify_bundle.py --mode gui
```

For the complete frozen UI check, install Playwright and pngjs in a separate
directory, set `NODE_PATH` to its `node_modules`, install Playwright's Chromium,
then run `python scripts/verify_frozen_ui.py`. GitHub Actions does this before
archiving.

The source launcher also accepts `ramancloud-desktop`. When installed outside the
checkout, pass `--frontend-dist /absolute/path/to/frontend/dist`; the root Python
wheel is not itself a frontend build. Frozen apps always use their bundled files
and reject this override. `desktop/build.py` validates all public assets and
research image references before running the onedir
[PyInstaller spec](https://pyinstaller.org/en/stable/spec-files.html). It collects
sample data with `collect_data_files('ramancloud_backend')`, not from legacy
absolute server paths. Unused Torch denoising models, MCP, Qt, CEF, and Numba are
excluded. There is no cross-compilation.

Build outputs stay under `desktop/build/`, `desktop/dist/`, and
`desktop/artifacts/`. Archive only after the API, native GUI, and browser UI
checks pass:

```bash
python desktop/artifacts.py archive --platform windows-x64
```

Use `macos-x64` or `macos-arm64` on the corresponding Mac. Mac archives use `ditto`
to preserve app metadata and executable modes. Linux freezing is supported only
for local API/static verification, not as a published native GUI target.

## Runtime Checks

```bash
RamanCloud.exe --smoke-test --require-frozen --smoke-report smoke.json
RamanCloud.exe --gui-smoke-test --require-frozen --smoke-report native.json
RamanCloud.exe --serve --ready-file ready.json
```

On Mac use `RamanCloud.app/Contents/MacOS/RamanCloud` instead of `RamanCloud.exe`.
`--smoke-test` never imports a GUI engine. It exercises the real HTTP socket,
original and prefixed APIs, full UI routes, every asset hash, globe JSON, all
spectral and mapping demos, each active algorithm, batch processing, uploads,
TXT/ZIP exports, split/merge/conversion, local statistics, and shutdown. Frozen
checks run from an unrelated working directory and require `sys.frozen`.

`--gui-smoke-test` opens the real native engine, checks the rendered React root,
WebGL2 pixel output, API processing, and the injected Blob bridge's exact TXT/ZIP
bytes. Save destinations are substituted to keep this check noninteractive; it
does **not** automate the OS save picker. Manually check file upload and native
save-dialog cancellation on both OS families before shipping a new renderer
version. Its window closes automatically and it exits nonzero on failures.

`--serve` / `--headless` prints the full loopback UI URL and writes atomic JSON
`{"url": "http://127.0.0.1:<port>/preprocessing/", "pid": 123, "frozen": true}`.
It waits for SIGINT/SIGTERM (or CTRL_BREAK on Windows). This mode uses normal
browser downloads; add `--native-downloads` for a browser test that supplies a
`window.pywebview.api` stub. The native window enables `ALLOW_DOWNLOADS` and also
uses an injected early-loading bridge for detached Blob anchors, immediate URL
revocation, TXT, and ZIP files. Downloads stream in bounded chunks to a native
save dialog, use atomic replacement, and show failures rather than silently
discarding exports. The underlying frontend files are unchanged.

The server reserves a loopback socket **before** starting Uvicorn, disables proxy
forwarding, rejects foreign Host/Origin headers, owns backend startup/shutdown,
and joins the server thread on exit. A content policy prevents remote runtime
media requests. External publication/reference links still open in the system
browser when selected; their remote contents are not bundled. The original
FastAPI Swagger/ReDoc pages retain their upstream CDN behavior and are not part
of the offline frontend.

## Data And Diagnostics

Writable application data and rotating `logs/desktop.log` live at:

- Windows: `%LOCALAPPDATA%\RamanCloud`
- macOS: `~/Library/Application Support/RamanCloud`
- Linux checks: `${XDG_DATA_HOME:-~/.local/share}/ramancloud-desktop`

`--data-dir <path>` overrides this location. WebView state and local visit
statistics live there, never beside a read-only installed executable. Uploaded
spectra and mapping caches remain in backend memory; closing the app clears
them. CLI smoke runs use temporary data unless given `--data-dir`. A startup
failure logs its traceback and shows a readable native error dialog for GUI
launches. Source and headless checks also report failures on stderr and exit 1.
CI keeps JSON smoke reports, screenshots, and runtime logs as diagnostic artifacts.

## Release Pipeline

The tag workflow builds on native Windows, Intel Mac, and Apple Silicon Mac
runners. Publication requires all three builds to pass API, native WebView,
Blob-export, and offline browser workflow checks. The MCP wheel and source
distribution must also pass the shared backend tests and a fresh installed-wheel
protocol check. All downloads have SHA-256 checksums. Manual workflow runs only
build and test, without publishing.

The native shell does not bundle MCP, a second browser, or unused machine-learning
frameworks. The globe geometry, research images, tutorial, and demo spectra are
local assets. External article links still require a network connection.

Trusted OS signing requires the maintainer's own credentials. The PyInstaller
spec accepts `RAMANCLOUD_CODESIGN_IDENTITY` and `RAMANCLOUD_ENTITLEMENTS_FILE`;
Developer ID import/notarization and Windows Authenticode signing are not
configured for this release. Missing WebView2 runtimes can be installed using
Microsoft's offline installer, independently of the app archive.
