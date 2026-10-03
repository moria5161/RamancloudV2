"""Console entry point and native GUI launcher; no GUI imports in headless modes."""

import argparse
import contextlib
import json
import logging
import os
import signal
import sys
import tempfile
import threading
from importlib.metadata import PackageNotFoundError, version
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .runtime import RuntimeServer, frontend_directory

logger = logging.getLogger(__name__)


def application_version():
    try:
        return version("ramancloud")
    except PackageNotFoundError:
        return "unknown"


def default_data_directory():
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "RamanCloud"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "RamanCloud"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "ramancloud-desktop"


def configure_logging(directory):
    logs = directory / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    filename = logs / "desktop.log"
    handler = RotatingFileHandler(filename, maxBytes=3 * 1024**2, backupCount=3, encoding="utf-8")
    handlers = [handler]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers, force=True)
    return filename


def write_json(path, data):
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def serve(runtime, ready_file=None):
    stopped = threading.Event()
    previous = {}
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is not None:
            previous[sig] = signal.signal(sig, lambda signum, frame: stopped.set())
    try:
        if ready_file:
            write_json(ready_file, {"url": runtime.url, "pid": os.getpid(), "frozen": bool(getattr(sys, "frozen", False))})
        if sys.stdout is not None:
            print(runtime.url, flush=True)
        while not stopped.wait(0.25):
            if runtime.error or not runtime.thread.is_alive():
                raise RuntimeError("Desktop API stopped unexpectedly") from runtime.error
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if ready_file:
            Path(ready_file).expanduser().resolve().unlink(missing_ok=True)


def show_failure(message):
    # A failed engine import must not require that same engine to show the error.
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "RamanCloud could not start", 0x10)
        elif sys.platform == "darwin":
            import subprocess
            subprocess.run(["osascript", "-e", 'on run argv\ndisplay alert "RamanCloud could not start" message (item 1 of argv) as critical\nend run', message], timeout=30, check=False)
    except Exception:
        logger.exception("Could not display failure dialog")


def require_webview2():
    import winreg

    key = r"Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    for hive, access in ((winreg.HKEY_CURRENT_USER, winreg.KEY_READ),
                         (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_READ | winreg.KEY_WOW64_32KEY)):
        try:
            with winreg.OpenKey(hive, key, 0, access) as handle:
                installed, _ = winreg.QueryValueEx(handle, "pv")
                if isinstance(installed, str) and any(part.isdigit() and int(part) > 0 for part in installed.split(".")):
                    return
        except OSError:
            pass
    raise RuntimeError("Microsoft Edge WebView2 Runtime is not installed. For offline setup, install Microsoft's x64 Evergreen Standalone Installer, then restart RamanCloud. The Edge browser alone is not sufficient.")


def open_window(runtime, data_directory, debug=False, gui_smoke=False):
    if sys.platform not in ("win32", "darwin"):
        raise RuntimeError("Native desktop releases support Windows and macOS. Use --serve or --smoke-test on Linux.")
    if sys.platform == "win32":
        require_webview2()
    from .bridge import DownloadBridge
    import webview

    bridge = DownloadBridge()
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.settings["ALLOW_FILE_URLS"] = False
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    window = webview.create_window("RamanCloud", runtime.url, js_api=bridge,
                                   width=1280, height=860, min_size=(800, 600), text_select=True)
    bridge._attach(window)
    verify, gui_report, done = (None, None, None)
    if gui_smoke:
        from .gui_smoke import prepare_gui_smoke
        verify, gui_report, done = prepare_gui_smoke(window, bridge, data_directory)
    stopped = threading.Event()
    window.events.closed += stopped.set

    def before_close():
        # Cocoa Cmd-Q can terminate the process without returning from start().
        stopped.set()
        bridge._close()
        runtime.stop()

    window.events.closing += before_close

    def monitor():
        while not stopped.wait(0.5):
            if runtime.error or not runtime.thread.is_alive():
                logger.error("API server stopped while the native window was open")
                window.destroy()
                return

    watcher = threading.Thread(target=monitor, name="ramancloud-monitor", daemon=True)
    watcher.start()
    try:
        # No MSHTML/IE fallback: Plotly/Three/React require a modern engine.
        webview.start(func=verify, gui="edgechromium" if sys.platform == "win32" else "cocoa", debug=debug,
                      private_mode=False, storage_path=str(data_directory / "webview"))
        if runtime.error or (not runtime.thread.is_alive() and not stopped.is_set()):
            raise RuntimeError("Desktop API stopped unexpectedly") from runtime.error
        if gui_smoke:
            if not done.is_set() or not gui_report.get("ok"):
                raise RuntimeError(gui_report.get("error", "Native window closed before completing its smoke test"))
            return {"native": gui_report}
    finally:
        stopped.set()
        watcher.join(timeout=2)
        bridge._close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="RamanCloud native desktop application")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--smoke-test", action="store_true", help="Test the actual local runtime without a GUI and exit")
    modes.add_argument("--serve", "--headless", action="store_true", help="Serve the same app without a GUI until SIGINT/SIGTERM")
    modes.add_argument("--gui-smoke-test", action="store_true", help="Open and test the native engine noninteractively, then exit")
    parser.add_argument("--require-frozen", action="store_true", help="Fail unless running the PyInstaller executable")
    parser.add_argument("--smoke-report", type=Path, help="Write the smoke result as JSON, including failures")
    parser.add_argument("--ready-file", type=Path, help="In serve mode write URL/PID JSON when ready")
    parser.add_argument("--native-downloads", action="store_true", help="In serve mode enable the native bridge (browser tests must supply a pywebview.api stub)")
    parser.add_argument("--frontend-dist", type=Path, help="Source mode only: use an existing frontend build")
    parser.add_argument("--data-dir", type=Path, help="Override the writable application data directory")
    parser.add_argument("--debug", action="store_true", help="Enable native WebView developer tools")
    parser.add_argument("--version", action="version", version="RamanCloud " + application_version())
    args = parser.parse_args(argv)
    if args.ready_file and not args.serve:
        parser.error("--ready-file requires --serve")
    if args.smoke_report and not (args.smoke_test or args.gui_smoke_test):
        parser.error("--smoke-report requires --smoke-test or --gui-smoke-test")
    if args.native_downloads and not args.serve:
        parser.error("--native-downloads requires --serve")
    runtime = None
    report = {"ok": False, "version": application_version(), "frozen": bool(getattr(sys, "frozen", False))}
    failure = None
    log_path = None
    # Smoke runs leave scientific files and analytics in temporary storage only.
    testing = args.smoke_test or args.gui_smoke_test
    temporary = tempfile.TemporaryDirectory(prefix="ramancloud-smoke-") if testing and not args.data_dir else contextlib.nullcontext(None)
    with temporary as temporary_directory:
        try:
            directory = args.data_dir.expanduser().resolve() if args.data_dir else Path(temporary_directory) if temporary_directory else default_data_directory()
            log_path = configure_logging(directory)
            logger.info("RamanCloud %s, frozen=%s", report["version"], report["frozen"])
            if args.require_frozen and not report["frozen"]:
                raise RuntimeError("This check must run the frozen application, not a Python source launcher")
            frontend = frontend_directory(args.frontend_dist)
            runtime = RuntimeServer(frontend, directory, native_downloads=args.native_downloads or not (args.serve or args.smoke_test))
            runtime.start()
            if args.smoke_test:
                from .smoke import run_smoke_test
                report.update(run_smoke_test(runtime, frontend))
            elif args.serve:
                serve(runtime, args.ready_file)
            else:
                result = open_window(runtime, directory, args.debug, args.gui_smoke_test)
                if result:
                    report.update(result)
        except KeyboardInterrupt:
            logger.info("Interrupted")
            failure = "Interrupted"
        except Exception as error:
            logger.exception("Desktop runtime failed")
            failure = str(error)
        finally:
            if runtime:
                try:
                    runtime.stop()
                except Exception as error:
                    logger.exception("Desktop shutdown failed")
                    failure = failure or str(error)
            if testing:
                report["ok"] = failure is None
                report["shutdown"] = failure is None and bool(runtime) and not runtime.thread.is_alive()
                if failure:
                    report["error"] = failure
                if args.smoke_report:
                    write_json(args.smoke_report, report)
                if sys.stdout is not None:
                    print(json.dumps(report, indent=2), flush=True)
            if failure and not (args.serve or testing):
                show_failure(f"{failure}\n\nLog: {log_path or 'Could not create a log file'}\n\nWindows needs Microsoft Edge WebView2 Runtime (.NET 4.6.2+). macOS uses the system WKWebView.")
            logging.shutdown()
    return 1 if failure else 0
