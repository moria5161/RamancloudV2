import { getLocale } from '../locale.js';
import React, { useEffect, useRef, useState } from 'react';
import { apiErrorMessage } from '../auth';
import './ModuleRecords.css';

export default function ModuleUploadHistory({ api, module, revision, txt, disabled, onSelect, onError, onLoading }) {
  const [sources, setSources] = useState([]), [busy, setBusy] = useState(false);
  const sequence = useRef(0);
  useEffect(() => {
    let cancelled = false;
    api.get(`/${module}/sources`)
      .then(({ data }) => { if (!cancelled) setSources(data); })
      .catch(error => { if (!cancelled) onError(apiErrorMessage(error)); });
    return () => { cancelled = true; };
  }, [api, module, revision]);
  useEffect(() => () => { sequence.current += 1; }, []);
  async function load(id) {
    if (!id) return;
    const current = ++sequence.current;
    setBusy(true); onLoading?.(true);
    try {
      const { data } = await api.get(`/${module}/sources/${id}`);
      if (current !== sequence.current) return;
      onSelect(data);
    } catch (error) { if (current === sequence.current) onError(apiErrorMessage(error)); }
    finally { if (current === sequence.current) { setBusy(false); onLoading?.(false); } }
  }
  return <div className="module-upload-history">
    {!!sources.length && <label>{txt('本模块上传记录', 'Uploads in this module')}<select aria-label={txt('本模块上传记录', 'Uploads in this module')} disabled={disabled || busy} value="" onChange={event => load(event.target.value)}><option value="">{txt('重新选择已上传的光谱', 'Reuse an uploaded spectrum')}</option>{sources.map(item => <option value={item.id} key={item.id}>{item.source_name} · {new Date(item.created_at).toLocaleString(getLocale())}</option>)}</select></label>}
  </div>;
}
