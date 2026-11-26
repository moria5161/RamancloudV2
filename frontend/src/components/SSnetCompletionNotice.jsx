import React, { useEffect, useState } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { API_BASE } from '../apiBase';
import { useAuth } from '../auth';
import { usePreferences } from '../i18n';

export const SSNET_COMPLETION_VIEWED = 'ramancloud:ssnet-completion-viewed';

export default function SSnetCompletionNotice() {
  const { token } = useAuth();
  const { language } = usePreferences();
  const [notices, setNotices] = useState([]);
  const latest = notices[0];

  useEffect(() => {
    let request;
    async function refresh() {
      if (document.hidden) return;
      request?.abort();
      const current = new AbortController();
      request = current;
      try {
        const { data } = await axios.get(`${API_BASE}/ssnet/completions`, {
          headers: { Authorization: `Bearer ${token}` }, signal: current.signal,
        });
        if (!current.signal.aborted) setNotices(data);
      } catch {
        // Keep the current reminder visible until the next refresh succeeds.
      }
    }

    refresh();
    const timer = setInterval(refresh, 15000);
    document.addEventListener('visibilitychange', refresh);
    window.addEventListener(SSNET_COMPLETION_VIEWED, refresh);
    return () => {
      request?.abort();
      clearInterval(timer);
      document.removeEventListener('visibilitychange', refresh);
      window.removeEventListener(SSNET_COMPLETION_VIEWED, refresh);
    };
  }, [token]);

  if (!latest) return null;
  const zh = language === 'zh';
  const title = notices.length > 1
    ? (zh ? `${notices.length} 项 SSnet 任务已完成` : `${notices.length} SSnet tasks completed`)
    : latest.kind === 'train'
      ? (zh ? 'SSnet 标准品模型已就绪' : 'SSnet reference model is ready')
      : (zh ? 'SSnet 混合谱解析已完成' : 'SSnet mixture analysis completed');

  return (
    <div className="glass flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-white/10 px-4 py-2 text-sm text-gray-200" data-ssnet-completion>
      <div role="status" className="flex min-w-0 items-center gap-2">
        <CheckCircle2 size={16} className="shrink-0 text-emerald-500" />
        <span className="truncate">{title}{notices.length === 1 ? ` · ${latest.name}` : ''}</span>
      </div>
      <Link className="text-indigo-400 hover:underline" to={`/spectral-unmixing?job=${encodeURIComponent(latest.id)}`}>
        {zh ? '查看结果' : 'View result'}
      </Link>
    </div>
  );
}
