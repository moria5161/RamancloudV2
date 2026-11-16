import process from 'process';
import { Buffer } from 'buffer';

// Ketcher's browser dependencies use Node-compatible utility globals.
globalThis.process = process;
globalThis.Buffer = Buffer;
globalThis.global = globalThis;
import('./structure-editor-app.jsx').catch(error => {
  document.getElementById('root').textContent = 'Molecular editor could not load.';
  window.parent.postMessage({ channel: 'ramancloud-structure', type: 'error', error: error.message }, window.location.origin);
});
