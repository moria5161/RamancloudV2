import { useEffect, useRef } from 'react';

const SESSION_TIMEOUT = 30 * 60 * 1000;
const STORAGE_KEY = 'ramancloud-visit-session';
const PATHS = new Set(['/', '/spectral', '/hyperspectral', '/extra-tools', '/tutorial', '/contributors']);

export default function useVisitTracking(path) {
  const navigation = useRef(null);
  const fallback = useRef(null);
  useEffect(() => {
    if (!PATHS.has(path) || navigator.doNotTrack === '1' || navigator.globalPrivacyControl === true) return;
    if (!navigation.current || navigation.current.path !== path) {
      navigation.current = { path, event_id: crypto.randomUUID() };
    }
    const event = navigation.current;
    let stopped = false;
    let retry;
    const send = async (attempt = 0) => {
      let session = fallback.current;
      try { session = JSON.parse(sessionStorage.getItem(STORAGE_KEY)) || session; } catch { /* Storage may be disabled. */ }
      if (!session || Date.now() - session.lastSeen >= SESSION_TIMEOUT) session = { id: crypto.randomUUID() };
      session.lastSeen = Date.now();
      fallback.current = session;
      try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session)); } catch { /* Keep an in-memory session. */ }
      try {
        const response = await fetch(`${import.meta.env.BASE_URL}api/visits/pageview`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, keepalive: true,
          body: JSON.stringify({ ...event, session_id: session.id }),
        });
        if (!response.ok) throw new Error('Statistics unavailable');
        window.dispatchEvent(new Event('ramancloud:pageview-recorded'));
      } catch {
        if (!stopped && attempt < 2) retry = setTimeout(() => send(attempt + 1), 3000 * (attempt + 1));
      }
    };
    const timer = setTimeout(send, 250);
    return () => { stopped = true; clearTimeout(timer); clearTimeout(retry); };
  }, [path]);
}
