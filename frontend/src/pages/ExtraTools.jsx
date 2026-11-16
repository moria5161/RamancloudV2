import React, { useRef, useState } from 'react';
import axios from 'axios';
import { Archive, ArrowRightLeft, Combine, Download, Scissors, Upload, Wrench } from 'lucide-react';
import { usePreferences } from '../i18n';
import UploadSharingNotice from '../components/UploadSharingNotice';
import { requestErrorDetail } from '../utils/requestError';

import { API_BASE } from '../utils/apiBase';

const tools = [
  { id: 'split', labelKey: 'splitMapping', descKey: 'splitMappingDesc', icon: Scissors },
  { id: 'merge', labelKey: 'mergeSpectra', descKey: 'mergeSpectraDesc', icon: Combine },
  { id: 'convert', labelKey: 'formatConversion', descKey: 'conversion', icon: ArrowRightLeft },
];

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(new Blob([blob]));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ExtraTools() {
  const { t } = usePreferences();
  const [mode, setMode] = useState('split');
  const [instrument, setInstrument] = useState('Horiba');
  const [conversion, setConversion] = useState('horiba_to_nanophoton');
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [message, setMessage] = useState('');
  const [failed, setFailed] = useState(false);
  const inputRef = useRef(null);

  const multiple = mode === 'merge';
  const accept = mode === 'merge' ? '.txt,.asc,.csv' : '.txt';

  const resetFiles = () => {
    setSelectedFiles([]);
    if (inputRef.current) inputRef.current.value = '';
  };

  const handleMode = (nextMode) => {
    if (isRunning) return;
    setMode(nextMode);
    setMessage('');
    resetFiles();
  };

  const runTool = async () => {
    if (!selectedFiles.length) {
      setMessage(t('uploadRequired'));
      return;
    }
    setIsRunning(true);
    setFailed(false);
    setMessage('');
    try {
      const formData = new FormData();
      formData.append('share_data', 'true');
      let endpoint = '';
      let filename = '';

      if (mode === 'split') {
        formData.append('file', selectedFiles[0]);
        formData.append('instrument', instrument);
        endpoint = `${API_BASE}/tools/split`;
        filename = 'split_files.zip';
      } else if (mode === 'merge') {
        selectedFiles.forEach((file) => formData.append('files', file));
        endpoint = `${API_BASE}/tools/merge`;
        filename = 'merged_mapping.txt';
      } else {
        formData.append('file', selectedFiles[0]);
        formData.append('conversion', conversion);
        endpoint = `${API_BASE}/tools/convert`;
        const stem = selectedFiles[0].name.replace(/\.[^.]+$/, '');
        filename = conversion === 'horiba_to_nanophoton' ? `${stem}_to_Nanophoton.txt` : `${stem}_to_Horiba.txt`;
      }

      const { data, headers } = await axios.post(endpoint, formData, { responseType: 'blob', timeout: 600000 });
      saveBlob(data, filename);
      setMessage(headers['x-ramancloud-data-sharing'] === 'failed' ? `${t('toolDone')} ${t('archiveFailed')}` : t('toolDone'));
    } catch (error) {
      const detail = await requestErrorDetail(error);
      setFailed(true);
      setMessage(`${t('requestFailed')}${detail ? ` ${detail}` : ''}`);
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto px-4 sm:px-8 py-10 space-y-8 animate-fade-in">
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <Wrench className="w-6 h-6 shrink-0 text-indigo-400" />
            <h1 className="text-2xl font-bold text-white">{t('extraTools')}</h1>
          </div>
          <p className="text-sm text-gray-400 max-w-2xl">
            {t('extraToolsDesc')}
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {tools.map(({ id, labelKey, descKey, icon: Icon }) => (
            <button
              key={id}
              disabled={isRunning}
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
                  <div className="text-sm font-semibold text-gray-200">{t(labelKey)}</div>
                  <div className="text-xs text-gray-500">
                    {id === 'convert' ? 'Horiba / Nanophoton' : t(descKey)}
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
                {mode === 'split' && t('splitMappingTitle')}
                {mode === 'merge' && t('mergeSpectraTitle')}
                {mode === 'convert' && t('conversionTitle')}
              </h2>
              <p className="text-xs text-gray-500 mt-1">
                {mode === 'split' && t('splitMappingHelp')}
                {mode === 'merge' && t('mergeSpectraHelp')}
                {mode === 'convert' && t('conversionHelp')}
              </p>
            </div>
            <Archive className="w-5 h-5 text-indigo-400" />
          </div>

          <UploadSharingNotice />
          <div className="flex flex-wrap items-center gap-4">
            {mode === 'split' && (
              <label className="space-y-1.5">
                <span className="text-xs text-gray-500">{t('instrument')}</span>
                <select disabled={isRunning} value={instrument} onChange={(e) => setInstrument(e.target.value)} className="block px-3 py-2 rounded-lg border border-white/10 text-sm">
                  <option value="Horiba">Horiba</option>
                  <option value="Renishaw">Renishaw</option>
                  <option value="Nanophoton">Nanophoton</option>
                </select>
              </label>
            )}

            {mode === 'convert' && (
              <label className="space-y-1.5">
                <span className="text-xs text-gray-500">{t('conversion')}</span>
                <select disabled={isRunning} value={conversion} onChange={(e) => setConversion(e.target.value)} className="block px-3 py-2 rounded-lg border border-white/10 text-sm">
                  <option value="horiba_to_nanophoton">{t('horibaToNanophoton')}</option>
                  <option value="nanophoton_to_horiba">{t('nanophotonToHoriba')}</option>
                </select>
              </label>
            )}

            <button
              disabled={isRunning}
              onClick={() => inputRef.current?.click()}
              className="liquid-button flex items-center gap-2 px-4 py-2 rounded-xl bg-white/5 text-gray-300 text-sm font-medium border border-white/5"
            >
              <Upload className="w-4 h-4" />
              {multiple ? t('uploadFiles') : t('uploadFile')}
            </button>

            <input
              ref={inputRef}
              type="file"
              disabled={isRunning}
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
                {t('noFileSelected')}
              </div>
            )}
          </div>

          {message && (
            <div role={failed ? 'alert' : 'status'} className={`rounded-lg border px-4 py-3 text-sm ${failed ? 'border-red-500/20 text-red-400' : 'border-indigo-500/20 text-gray-400'}`}>
              {message}
              {failed && <button disabled={isRunning} onClick={runTool} className="ml-3 text-indigo-400 underline">{t('retry')}</button>}
            </div>
          )}

          <div className="flex items-center justify-end">
            <button
              onClick={runTool}
              disabled={isRunning || !selectedFiles.length}
              className="liquid-button flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 text-white text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {isRunning ? t('running') : t('runTool')}
              <Download className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
