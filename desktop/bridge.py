"""Blob downloads work consistently in both WKWebView and WebView2."""

import base64
import binascii
import logging
import os
import tempfile
import threading
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)
MAX_DOWNLOAD_BYTES = 2 * 1024**3
CHUNK_BYTES = 512 * 1024

BRIDGE_JS = r"""(() => {
  'use strict';
  if (document.currentScript?.dataset.nativeDownloads !== 'true') return;
  const blobs = new Map();
  const create = URL.createObjectURL.bind(URL);
  const revoke = URL.revokeObjectURL.bind(URL);
  URL.createObjectURL = blob => {
    const url = create(blob);
    if (blob instanceof Blob) blobs.set(url, blob);
    return url;
  };
  URL.revokeObjectURL = url => { blobs.delete(url); revoke(url); };
  const ready = () => new Promise((resolve, reject) => {
    if (window.pywebview?.api) { resolve(window.pywebview.api); return; }
    const done = () => { clearTimeout(timer); resolve(window.pywebview.api); };
    const timer = setTimeout(() => {
      window.removeEventListener('pywebviewready', done);
      reject(new Error('The native save dialog is unavailable. Restart RamanCloud.'));
    }, 20000);
    window.addEventListener('pywebviewready', done, { once: true });
  });
  const encode = bytes => {
    let binary = '';
    for (let offset = 0; offset < bytes.length; offset += 8192)
      binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
    return btoa(binary);
  };
  const check = result => {
    if (!result || result.error) throw new Error(result?.error || 'Native save failed.');
    return result;
  };
  let pending = Promise.resolve();
  const save = (blob, filename) => {
    // Capture the Blob before the caller revokes its URL, including detached anchors.
    pending = pending.then(async () => {
      const api = await ready();
      const start = check(await api.begin_download(filename, blob.size));
      if (start.cancelled) return;
      try {
        let sequence = 0;
        for (let offset = 0; offset < blob.size; offset += 524288) {
          const bytes = new Uint8Array(await blob.slice(offset, offset + 524288).arrayBuffer());
          check(await api.write_download(start.id, sequence++, encode(bytes)));
        }
        check(await api.finish_download(start.id));
      } catch (error) {
        await api.abort_download(start.id);
        throw error;
      }
    }).catch(error => {
      console.error('RamanCloud export failed', error);
      window.alert('RamanCloud could not save the download.\n' + error.message);
    });
  };
  const intercept = anchor => {
    if (!anchor || !anchor.hasAttribute('download') || !anchor.href.startsWith('blob:')) return false;
    const blob = blobs.get(anchor.href);
    if (!blob) {
      window.alert('RamanCloud could not read this download. Please export it again.');
      return true;
    }
    save(blob, anchor.download || 'download');
    return true;
  };
  const click = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function (...args) {
    if (!intercept(this)) return click.apply(this, args);
  };
  document.addEventListener('click', event => {
    const anchor = event.target.closest?.('a[download]');
    if (intercept(anchor)) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
})();
"""


class DownloadBridge:
    def __init__(self):
        self._window = None
        self._sessions = {}
        self._lock = threading.RLock()

    def _attach(self, window):
        self._window = window

    def begin_download(self, filename, size):
        try:
            if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= MAX_DOWNLOAD_BYTES:
                raise ValueError("Download must be no larger than 2 GiB")
            if not self._window:
                raise RuntimeError("Native window is not ready")
            import webview

            name = str(filename).replace("\\", "/").rsplit("/", 1)[-1]
            name = "".join(c for c in name if ord(c) >= 32 and c not in '<>:"|?*').strip(". ") or "download"
            with self._lock:
                if self._sessions:
                    raise RuntimeError("Another download is still being saved")
                selected = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename=name)
                if not selected:
                    return {"cancelled": True}
                destination = Path(selected if isinstance(selected, str) else selected[0])
                stream = tempfile.NamedTemporaryFile(prefix=".ramancloud-", dir=destination.parent, delete=False)
                token = uuid.uuid4().hex
                self._sessions[token] = {"stream": stream, "destination": destination, "size": size, "written": 0, "sequence": 0}
            return {"id": token}
        except Exception as error:
            logger.exception("Could not open native save dialog")
            return {"error": str(error)}

    def write_download(self, token, sequence, encoded):
        try:
            if not isinstance(encoded, str) or len(encoded) > 4 * ((CHUNK_BYTES + 2) // 3):
                raise ValueError("Invalid download chunk size")
            data = base64.b64decode(encoded, validate=True)
            with self._lock:
                session = self._sessions[token]
                if sequence != session["sequence"] or len(data) > CHUNK_BYTES:
                    raise ValueError("Download chunks arrived out of order")
                if session["written"] + len(data) > session["size"]:
                    raise ValueError("Download exceeds its declared size")
                session["stream"].write(data)
                session["written"] += len(data)
                session["sequence"] += 1
            return {"ok": True}
        except (KeyError, ValueError, TypeError, OSError, binascii.Error) as error:
            logger.exception("Could not write download chunk")
            self.abort_download(token)
            return {"error": str(error)}

    def finish_download(self, token):
        try:
            with self._lock:
                session = self._sessions[token]
                if session["written"] != session["size"]:
                    raise ValueError("Download is incomplete")
                stream = session["stream"]
                stream.flush()
                os.fsync(stream.fileno())
                stream.close()
                Path(stream.name).replace(session["destination"])
                del self._sessions[token]
            logger.info("Saved download (%s bytes)", session["size"])
            return {"ok": True}
        except (KeyError, ValueError, OSError) as error:
            logger.exception("Could not finish download")
            self.abort_download(token)
            return {"error": str(error)}

    def abort_download(self, token):
        with self._lock:
            session = self._sessions.pop(token, None)
            if session:
                session["stream"].close()
                Path(session["stream"].name).unlink(missing_ok=True)
        return {"ok": True}

    def _close(self):
        with self._lock:
            for token in list(self._sessions):
                self.abort_download(token)
