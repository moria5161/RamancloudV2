import { useRef, useState } from 'react';

export default function useWorkspaceTask(t) {
  const lock = useRef(false);
  const retryAction = useRef(null);
  const [phase, setPhase] = useState(null);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);

  const run = async (initialPhase, action) => {
    if (lock.current) return;
    lock.current = true;
    retryAction.current = () => run(initialPhase, action);
    setError(null);
    setProgress(null);
    setPhase(initialPhase);
    try {
      await action({
        setPhase,
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
      const detail = failure.response?.data?.detail || failure.response?.data?.msg;
      setError(typeof detail === 'string' ? `${t('requestFailed')} ${detail}` : t('requestFailed'));
    } finally {
      lock.current = false;
      setPhase(null);
      setProgress(null);
    }
  };

  return { run, phase, setPhase, progress, error, setError, busy: phase !== null, retry: () => retryAction.current?.() };
}
