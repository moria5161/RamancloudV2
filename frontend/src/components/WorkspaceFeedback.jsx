import React from 'react';
import { AlertCircle, Loader2, RotateCcw, X } from 'lucide-react';
import { usePreferences } from '../i18n';

export default function WorkspaceFeedback({ task, error, onDismiss }) {
  const { t } = usePreferences();
  const message = task.error || error;
  return (
    <>
      {task.busy && (
        <div className="workspace-busy" role="status" aria-live="polite">
          <div className="glass task-status">
            <Loader2 className="w-5 h-5 animate-spin" />
            <span>{t(task.phase)}{task.progress != null ? ` ${task.progress}%` : ''}</span>
            {task.progress != null && <progress value={task.progress} max="100" aria-label={t('uploadingData')} />}
          </div>
        </div>
      )}
      {message && !task.busy && (
        <div className="workspace-error glass" role="alert">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{message}</span>
          {task.error && <button onClick={task.retry}><RotateCcw className="w-4 h-4" />{t('retry')}</button>}
          <button title={t('dismiss')} aria-label={t('dismiss')} onClick={() => { task.setError(null); onDismiss?.(); }}><X className="w-4 h-4" /></button>
        </div>
      )}
    </>
  );
}
