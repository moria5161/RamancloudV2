"""Noninteractive native-engine checks, using chosen destinations instead of OS dialogs."""

import base64
import io
import json
import threading
import time
import tempfile
import zipfile
from pathlib import Path


class SmokeDialog:
    def __init__(self, directory):
        self._directory = directory

    def create_file_dialog(self, dialog_type, save_filename="", **kwargs):
        return (str(self._directory / save_filename),)


def prepare_gui_smoke(window, bridge, directory, allow_webgl_fallback=False):
    parent = Path(directory)
    parent.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="native-exports-", dir=parent))
    bridge._attach(SmokeDialog(directory))
    text = b"100\t1\n200\t2\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("spectrum.txt", text)
    expected = {"native-smoke.txt": text, "native-smoke.zip": buffer.getvalue()}
    report = {"ok": False}
    done = threading.Event()
    loaded = threading.Event()
    window.events.loaded += loaded.set
    fixtures = json.dumps({name: base64.b64encode(data).decode("ascii") for name, data in expected.items()})

    def verify():
        try:
            if not loaded.wait(45):
                raise TimeoutError("Native window did not load its local document")
            script = r"""(async () => {
              const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
              for (let i = 0; i < 100 && (!window.pywebview?.api || !document.querySelector('#root')?.children.length); i++) await wait(100);
              if (!window.pywebview?.api || !document.querySelector('#root')?.children.length) throw new Error('Native bridge or React UI did not load');
              const response = await fetch('/preprocessing/api/demo/tutorial');
              const demo = await response.json();
              const processed = await (await fetch('/preprocessing/api/process', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({...demo.data, steps: [{type:'denoise', method:'sg'}]})
              })).json();
              if (processed.code !== 0 || !processed.data.intensity.length) throw new Error('Native engine API integration failed');
              const until = async (predicate, message) => {
                for (let i = 0; i < 200; i++) { if (predicate()) return; await wait(100); }
                throw new Error(message);
              };
              await until(() => !document.querySelector('.welcome-screen'), 'Welcome did not close');
              const link = name => Array.from(document.querySelectorAll('a')).find(item => item.textContent.trim() === name);
              const button = (root, name) => Array.from(root.querySelectorAll('button')).find(item => item.textContent.trim() === name);
              link('Spectral Processing').click();
              await until(() => button(document, 'Demo - Bacterial Spectrum'), 'Native spectral workspace did not open');
              button(document, 'Demo - Bacterial Spectrum').click();
              const plot = () => document.querySelector('.workspace-route:not([hidden]) .js-plotly-plot');
              await until(() => plot()?.data?.length, 'Native raw spectral chart did not render');
              const dock = document.querySelector('.workspace-route:not([hidden]) .control-dock');
              button(dock, 'Denoise').click();
              await until(() => !button(dock, 'Run Pipeline').disabled, 'Native pipeline did not become ready');
              button(dock, 'Run Pipeline').click();
              await until(() => plot()?.data?.length >= 2 && plot().querySelectorAll('.scatterlayer .js-line').length >= 2, 'Native raw/processed SVG spectra did not render');
              link('Homepage').click();
              const canvas = document.createElement('canvas'); canvas.width = 8; canvas.height = 8;
              canvas.style.cssText = 'position:fixed;left:0;top:0;width:8px;height:8px';
              document.body.appendChild(canvas);
              const gl = canvas.getContext('webgl2', {preserveDrawingBuffer: true, antialias: false});
              if (!gl) throw new Error('Native engine cannot create WebGL2 (required by Three.js)');
              const pixel = new Uint8Array(4);
              for (let frame = 0; frame < 5; frame++) {
                gl.viewport(0, 0, canvas.width, canvas.height);
                gl.clearColor(1, 0.25, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT); gl.finish();
                await new Promise(requestAnimationFrame);
                gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
                if (pixel[0] >= 200 && pixel[1] >= 40) break;
              }
              const webgl = {pixel: Array.from(pixel), error: gl.getError(), lost: gl.isContextLost(), renderer: gl.getParameter(gl.RENDERER), version: gl.getParameter(gl.VERSION), drawingBuffer: [gl.drawingBufferWidth, gl.drawingBufferHeight]};
              const webgl2 = pixel[0] >= 200 && pixel[1] >= 40;
              if (!webgl2 && !(ALLOW_FALLBACK && webgl.lost && webgl.error === 37442)) throw new Error('Native WebGL canvas is blank: ' + JSON.stringify(webgl));
              canvas.remove();
              for (let i = 0; i < 100 && document.querySelector('.welcome-screen'); i++) await wait(100);
              const visits = document.querySelector('button[aria-label="View global visits"]');
              if (!visits) throw new Error('Homepage visits control did not render');
              visits.click();
              let globe, fallback = false;
              for (let i = 0; i < 150; i++) {
                document.querySelector('.visitor-globe-section')?.scrollIntoView({block: 'center'});
                globe = document.querySelector('.visitor-globe-section canvas');
                fallback = document.querySelector('.visitor-globe-placeholder')?.textContent.includes('The 3D globe is unavailable on this device. Region counts remain available.') || false;
                if (fallback) break;
                if (globe?.width && globe?.height) break;
                await wait(100);
              }
              if (fallback && !(ALLOW_FALLBACK && !webgl2 && webgl.lost)) throw new Error('Unexpected native globe fallback');
              const regions = document.querySelectorAll('.visitor-globe-region').length;
              if (fallback && regions < 20) throw new Error('GPU failure did not preserve the complete historical region list');
              if (!fallback && (!globe?.width || !globe?.height)) throw new Error('Native engine did not render the actual globe');
              if (!fallback) { globe.scrollIntoView({block: 'center'}); await wait(700); }
              const snapshot = document.createElement('canvas'); snapshot.width = globe?.width || 1; snapshot.height = globe?.height || 1;
              const ctx = snapshot.getContext('2d');
              let globeColors = 0;
              for (let frame = 0; !fallback && frame < 20 && globeColors < 30; frame++) {
                await new Promise(requestAnimationFrame);
                ctx.clearRect(0, 0, snapshot.width, snapshot.height);
                ctx.drawImage(globe, 0, 0);
                const data = ctx.getImageData(0, 0, snapshot.width, snapshot.height).data;
                const colors = new Set();
                for (let i = 0; i < data.length; i += 16) if (data[i + 3] > 100) colors.add(`${data[i] >> 4},${data[i + 1] >> 4},${data[i + 2] >> 4}`);
                globeColors = colors.size;
              }
              if (!fallback && globeColors < 30) throw new Error('Native globe has no mapped pixels: ' + globeColors);
              for (const [name, encoded] of Object.entries(FIXTURES)) {
                const bytes = Uint8Array.from(atob(encoded), value => value.charCodeAt(0));
                const url = URL.createObjectURL(new Blob([bytes]));
                const anchor = document.createElement('a'); anchor.href = url; anchor.download = name;
                anchor.click(); URL.revokeObjectURL(url);
              }
              return {react: true, api: true, spectral_svg: true, webgl2, webgl_diagnostics: webgl,
                      globe: !fallback, globe_fallback: fallback, globe_colors: globeColors, regions, bridge: true};
            })().then(result => {window.__ramancloudNativeSmoke = result;})
                .catch(error => {window.__ramancloudNativeSmoke = {error: String(error)};});
            """.replace("FIXTURES", fixtures).replace("ALLOW_FALLBACK", json.dumps(allow_webgl_fallback))
            window.run_js(script)
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                result = window.evaluate_js("window.__ramancloudNativeSmoke || null")
                if result and result.get("error"):
                    raise RuntimeError(result["error"])
                if result and all((directory / name).is_file() for name in expected):
                    for name, data in expected.items():
                        if (directory / name).read_bytes() != data:
                            raise AssertionError("Native export changed bytes: " + name)
                    report.update(result, ok=True, exports=[*expected], save_dialog="substituted-noninteractive-destinations")
                    return
                time.sleep(0.1)
            raise TimeoutError("Native API/Blob download checks did not finish")
        except Exception as error:
            report["error"] = str(error)
        finally:
            done.set()
            window.destroy()

    return verify, report, done
