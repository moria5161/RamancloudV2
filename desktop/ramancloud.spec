import os
import sys
from importlib.metadata import version
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

root = Path(SPECPATH).parent
desktop = root / "desktop"
datas = collect_data_files("ramancloud_backend", includes=["samples/*.txt", "historical_visits.json"])
datas += copy_metadata("ramancloud")
datas += [(str(root / "frontend/dist"), "frontend_dist"),
          (str(desktop / "build/desktop-assets.json"), ".")]
excludes = ["torch", "tensorflow", "numba", "llvmlite", "matplotlib", "IPython", "pytest",
            "ramancloud_mcp", "mcp", "denoising", "ramancloud_backend.denoising", "ramancloud_backend.analysis",
            "PyQt5", "PyQt6", "PySide2", "PySide6", "cefpython3", "gi",
            "webview.platforms.qt", "webview.platforms.gtk", "webview.platforms.cef", "webview.platforms.android",
            "webview.platforms.mshtml"]
hidden = ["uvicorn.logging", "uvicorn.loops.asyncio", "uvicorn.protocols.http.h11_impl", "uvicorn.lifespan.on"]
if sys.platform == "win32":
    hidden += ["webview.platforms.winforms", "webview.platforms.edgechromium", "pythonnet", "clr"]
    excludes += ["webview.platforms.cocoa"]
elif sys.platform == "darwin":
    hidden += ["webview.platforms.cocoa", "WebKit", "AppKit", "Foundation"]
    excludes += ["webview.platforms.winforms", "webview.platforms.edgechromium", "pythonnet", "clr"]
else:
    excludes += ["webview.platforms.cocoa", "webview.platforms.winforms", "webview.platforms.edgechromium"]

a = Analysis([str(desktop / "freeze_entry.py")], pathex=[str(root)], binaries=[], datas=datas,
             hiddenimports=hidden, hookspath=[], runtime_hooks=[], excludes=excludes, noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="RamanCloud", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False,
          console=sys.platform != "darwin", hide_console="hide-early" if sys.platform == "win32" else None,
          argv_emulation=False, target_arch=None, codesign_identity=os.environ.get("RAMANCLOUD_CODESIGN_IDENTITY"),
          entitlements_file=os.environ.get("RAMANCLOUD_ENTITLEMENTS_FILE"),
          icon=str(root / "frontend/public/logo-v1.png") if sys.platform in ("win32", "darwin") else None)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="RamanCloud")
if sys.platform == "darwin":
    app = BUNDLE(collection, name="RamanCloud.app", icon=str(root / "frontend/public/logo-v1.png"),
                 bundle_identifier="cn.edu.xmu.ramancloud.desktop", info_plist={
                     "CFBundleName": "RamanCloud", "CFBundleDisplayName": "RamanCloud",
                     "CFBundleShortVersionString": version("ramancloud"), "CFBundleVersion": version("ramancloud"),
                     "NSHighResolutionCapable": True,
                     "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
                 })
