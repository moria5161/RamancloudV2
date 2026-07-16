import React, { useRef, useState } from 'react';
import axios from 'axios';
import { Archive, ArrowRightLeft, Combine, Download, FileArchive, Scissors, Upload } from 'lucide-react';

const API_BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

const tools = [
  { id: 'split', label: 'Split Mapping', icon: Scissors },
  { id: 'merge', label: 'Merge Spectra', icon: Combine },
  { id: 'convert', label: 'Format Conversion', icon: ArrowRightLeft },
];

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(new Blob([blob]));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function errorMessage(error) {
  const detail = error?.response?.data?.detail;
  return detail || 'Tool execution failed. Please check the file format.';
}

export default function ExtraTools() {
  const [mode, setMode] = useState('split');
  const [instrument, setInstrument] = useState('Horiba');
  const [conversion, setConversion] = useState('horiba_to_nanophoton');
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [message, setMessage] = useState('');
  const inputRef = useRef(null);

  const multiple = mode === 'merge';
  const accept = mode === 'merge' ? '.txt,.asc,.csv' : '.txt';

  const resetFiles = () => {
    setSelectedFiles([]);
    if (inputRef.current) inputRef.current.value = '';
  };

  const handleMode = (nextMode) => {
    setMode(nextMode);
    setMessage('');
    resetFiles();
  };

  const runTool = async () => {
    if (!selectedFiles.length) {
      setMessage('Please upload the required file first.');
      return;
    }
    setIsRunning(true);
    setMessage('');
    try {
      const formData = new FormData();
      let endpoint = '';
      let filename = '';

      if (mode === 'split') {
        formData.append('file', selectedFiles[0]);
        formData.append('instrument', instrument);
        endpoint = `${API_BASE}/api/tools/split`;
        filename = 'split_files.zip';
      } else if (mode === 'merge') {
        selectedFiles.forEach((file) => formData.append('files', file));
        endpoint = `${API_BASE}/api/tools/merge`;
        filename = 'merged_mapping.txt';
      } else {
        formData.append('file', selectedFiles[0]);
        formData.append('conversion', conversion);
        endpoint = `${API_BASE}/api/tools/convert`;
        const stem = selectedFiles[0].name.replace(/\.[^.]+$/, '');
        filename = conversion === 'horiba_to_nanophoton' ? `${stem}_to_Nanophoton.txt` : `${stem}_to_Horiba.txt`;
      }

      const { data } = await axios.post(endpoint, formData, { responseType: 'blob' });
      saveBlob(data, filename);
      setMessage('Done. The result file has been generated.');
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto px-8 py-10 space-y-8 animate-fade-in">
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <FileArchive className="w-6 h-6 text-indigo-400" />
            <h1 className="text-2xl font-bold text-white">Extra Tools</h1>
          </div>
          <p className="text-sm text-gray-400 max-w-2xl">
            Utility tools for mapping file splitting, spectral file merging, and mapping format conversion between instruments.
          </p>
        </div>

        <div className="grid grid-cols-3 gap-4">
          {tools.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => handleMode(id)}
              className={`liquid-card glass rounded-xl p-5 border text-left transition-all ${
                mode === id ? 'border-indigo-500/30 bg-indigo-500/10' : 'border-white/5 bg-white/5'
              }`}
            >
              <div className="flex items-center gap-3">
                <div className="liquid-icon w-10 h-10 rounded-xl flex items-center justify-center">
                  <Icon className="w-5 h-5 text-indigo-400" />
                </div>
                <div>
                  <div className="text-sm font-semibold text-gray-200">{label}</div>
                  <div className="text-xs text-gray-500">
                    {id === 'split' && 'Mapping to individual spectra'}
                    {id === 'merge' && 'Spectra to one mapping table'}
                    {id === 'convert' && 'Horiba / Nanophoton'}
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>

        <div className="glass rounded-xl p-6 border border-white/5 space-y-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-gray-200">
                {mode === 'split' && 'Split Mapping Into Spectra'}
                {mode === 'merge' && 'Merge Files Into A Mapping'}
                {mode === 'convert' && 'Mapping Format Conversion'}
              </h2>
              <p className="text-xs text-gray-500 mt-1">
                {mode === 'split' && 'Upload one mapping file and download a zip package of single-spectrum text files.'}
                {mode === 'merge' && 'Upload multiple spectrum files and download one merged mapping text file.'}
                {mode === 'convert' && 'Upload one mapping file and convert its instrument-specific table format.'}
              </p>
            </div>
            <Archive className="w-5 h-5 text-indigo-400" />
          </div>

          <div className="flex flex-wrap items-center gap-4">
            {mode === 'split' && (
              <label className="space-y-1.5">
                <span className="text-xs text-gray-500">Instrument</span>
                <select value={instrument} onChange={(e) => setInstrument(e.target.value)} className="block px-3 py-2 rounded-lg border border-white/10 text-sm">
                  <option value="Horiba">Horiba</option>
                  <option value="Renishaw">Renishaw</option>
                  <option value="Nanophoton">Nanophoton</option>
                </select>
              </label>
            )}

            {mode === 'convert' && (
              <label className="space-y-1.5">
                <span className="text-xs text-gray-500">Conversion</span>
                <select value={conversion} onChange={(e) => setConversion(e.target.value)} className="block px-3 py-2 rounded-lg border border-white/10 text-sm">
                  <option value="horiba_to_nanophoton">Horiba to Nanophoton</option>
                  <option value="nanophoton_to_horiba">Nanophoton to Horiba</option>
                </select>
              </label>
            )}

            <button
              onClick={() => inputRef.current?.click()}
              className="liquid-button flex items-center gap-2 px-4 py-2 rounded-xl bg-white/5 text-gray-300 text-sm font-medium border border-white/5"
            >
              <Upload className="w-4 h-4" />
              {multiple ? 'Upload Files' : 'Upload File'}
            </button>

            <input
              ref={inputRef}
              type="file"
              accept={accept}
              multiple={multiple}
              onChange={(event) => setSelectedFiles(Array.from(event.target.files || []))}
              className="hidden"
            />
          </div>

          <div className="rounded-xl border border-white/5 bg-white/5 p-4 min-h-24">
            {selectedFiles.length ? (
              <div className="space-y-2">
                {selectedFiles.map((file) => (
                  <div key={`${file.name}-${file.size}`} className="flex items-center justify-between gap-3 text-sm">
                    <span className="truncate text-gray-300">{file.name}</span>
                    <span className="text-xs text-gray-500">{(file.size / 1024).toFixed(1)} KB</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="h-16 flex items-center justify-center text-sm text-gray-500">
                No file selected
              </div>
            )}
          </div>

          {message && (
            <div className="rounded-lg bg-indigo-500/10 border border-indigo-500/20 px-4 py-3 text-sm text-gray-400">
              {message}
            </div>
          )}

          <div className="flex items-center justify-end">
            <button
              onClick={runTool}
              disabled={isRunning}
              className="liquid-button flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 text-white text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {isRunning ? 'Running...' : 'Run Tool'}
              <Download className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
