import { useRef, useState } from 'react';
import { requestErrorDetail } from '../utils/requestError';

export default function useWorkspaceTask(t, retryProcessing) {
  const lock = useRef(false);
  const retryAction = useRef(null);
  const [phase, setPhase] = useState(null);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);
  const latestProcessing = useRef(retryProcessing);
  latestProcessing.current = retryProcessing;

  const run = async (initialPhase, action) => {
    if (lock.current) return;
    lock.current = true;
    retryAction.current = initialPhase === 'processing' && retryProcessing
      ? () => latestProcessing.current?.()
      : () => run(initialPhase, action);
    setError(null);
    setProgress(null);
    setPhase(initialPhase);
    try {
      await action({
        setPhase,
        setProgress,
        uploadProgress: event => {
          if (event.total) setProgress(Math.min(100, Math.round(event.loaded / event.total * 100)));
          if (event.total && event.loaded >= event.total) {
            setProgress(null);
            setPhase('readingData');
          }
        },
      });
      retryAction.current = null;
    } catch (failure) {
      const detail = await requestErrorDetail(failure);
      setError(failure?.response?.status === 429 ? t('requestRateLimited')
        : detail ? `${t('requestFailed')} ${detail}` : t('requestFailed'));
    } finally {
      lock.current = false;
      setPhase(null);
      setProgress(null);
    }
  };

  return { run, phase, setPhase, progress, error, setError, busy: phase !== null, retry: () => retryAction.current?.() };
}
