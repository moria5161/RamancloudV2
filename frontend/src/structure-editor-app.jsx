import React from 'react';
import { createRoot } from 'react-dom/client';
import { Editor } from 'ketcher-react';
import { StandaloneStructServiceProvider, STRUCT_SERVICE_INITIALIZED_EVENT } from 'ketcher-standalone';
import 'ketcher-react/dist/index.css';

const service = new StandaloneStructServiceProvider();
const send = data => window.parent.postMessage({ channel: 'ramancloud-structure', ...data }, window.location.origin);
let ketcher;
let engineReady = false;
const announceInitialized = () => { if (ketcher && engineReady) send({ type: 'initialized' }); };
window.addEventListener(STRUCT_SERVICE_INITIALIZED_EVENT, () => {
  engineReady = true;
  announceInitialized();
}, { once: true });
window.addEventListener('message', async event => {
  if (event.origin !== window.location.origin || event.source !== window.parent || event.data?.channel !== 'ramancloud-structure') return;
  const { type, requestId, smiles } = event.data;
  if (type === 'get-smiles') {
    try {
      if (!ketcher) throw new Error('Molecular editor is still loading.');
      send({ type: 'smiles', requestId, smiles: await ketcher.getSmiles() });
    } catch (error) { send({ type: 'smiles', requestId, error: error.message }); }
  } else if (type === 'set-smiles' && ketcher && typeof smiles === 'string') {
    try {
      await ketcher.setMolecule(smiles);
      send({ type: 'ready' });
    } catch (error) { send({ type: 'error', error: error.message }); }
  }
});

createRoot(document.getElementById('root')).render(<div style={{ height: '100vh', minHeight: 400 }}>
  <Editor staticResourcesUrl={import.meta.env.BASE_URL} structServiceProvider={service}
    errorHandler={error => send({ type: 'error', error: String(error) })}
    onInit={instance => {
      ketcher = instance;
      window.ketcher = instance;
      ketcher.editor.subscribe('change', () => send({ type: 'changed' }));
      announceInitialized();
    }} />
</div>);
