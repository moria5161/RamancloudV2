import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, Download, Waves } from 'lucide-react';
import { apiErrorMessage } from '../auth';

export default function ModuleInputActions({ api, module, source, txt, disabled, onError }) {
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate(), ref = source?.reference;
  if (!ref || source.kind === 'reference') return null;
  if (ref.workflow_id) return <Link className="sg-text-link" to={`/ai-analysis?task=${encodeURIComponent(ref.workflow_id)}${ref.version_id ? `&version=${encodeURIComponent(ref.version_id)}` : ''}`}><Waves size={14} />{txt('查看来源预处理', 'View source preprocessing')}<ArrowRight size={13} /></Link>;
  if (!ref.source_id) return null;
  async function download(kind) {
    setBusy(true);
    try {
      const { data } = await api.get(`/${module}/sources/${ref.source_id}/download`, { params: { kind }, responseType: 'blob' });
      const url = URL.createObjectURL(data), a = document.createElement('a');
      a.href = url; a.download = kind === 'original' ? source.name : 'standardized_spectrum.txt'; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { onError(apiErrorMessage(error)); }
    finally { setBusy(false); }
  }
  return <div className="sg-detail-actions">
    {['original', 'standardized'].map(kind => <button key={kind} disabled={disabled || busy} onClick={() => download(kind)}><Download size={14} />{kind === 'original' ? txt('原始文件', 'Original file') : txt('标准双列', 'Two-column data')}</button>)}
    <button disabled={disabled || busy} onClick={async () => {
      setBusy(true);
      try { const { data } = await api.post(`/${module}/sources/${ref.source_id}/preprocess`, {}); navigate(`/ai-analysis?task=${encodeURIComponent(data.id)}`); }
      catch (error) { onError(apiErrorMessage(error)); }
      finally { setBusy(false); }
    }}><Waves size={14} />{txt('复制到智能光谱处理', 'Copy to preprocessing')}<ArrowRight size={13} /></button>
  </div>;
}
