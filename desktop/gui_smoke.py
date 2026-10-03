"""Noninteractive native-engine checks, using chosen destinations instead of OS dialogs."""

import base64
import io
import json
import threading
import time
import zipfile
from pathlib import Path


class SmokeDialog:
    def __init__(self, directory):
        self._directory = directory

    def create_file_dialog(self, dialog_type, save_filename="", **kwargs):
        return (str(self._directory / save_filename),)


def prepare_gui_smoke(window, bridge, directory):
    directory = Path(directory) / "native-exports"
    directory.mkdir(parents=True, exist_ok=True)
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
              const canvas = document.createElement('canvas'); canvas.width = 8; canvas.height = 8;
              const gl = canvas.getContext('webgl2');
              if (!gl) throw new Error('Native engine cannot create WebGL2 (required by Three.js)');
              gl.clearColor(1, 0.25, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT);
              const pixel = new Uint8Array(4); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
              if (pixel[0] < 200 || pixel[1] < 40) throw new Error('Native WebGL canvas is blank');
              for (const [name, encoded] of Object.entries(FIXTURES)) {
                const bytes = Uint8Array.from(atob(encoded), value => value.charCodeAt(0));
                const url = URL.createObjectURL(new Blob([bytes]));
                const anchor = document.createElement('a'); anchor.href = url; anchor.download = name;
                anchor.click(); URL.revokeObjectURL(url);
              }
              return {react: true, api: true, webgl2: true, bridge: true};
            })().then(result => {window.__ramancloudNativeSmoke = result;})
                .catch(error => {window.__ramancloudNativeSmoke = {error: String(error)};});
            """.replace("FIXTURES", fixtures)
            window.run_js(script)
            deadline = time.monotonic() + 45
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
