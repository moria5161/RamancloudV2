import { useEffect, useState } from 'react';

const DEFAULT_WIDTH = 240;
const MIN_WIDTH = 200;
const MAX_WIDTH = 360;

function savedPreference(key, fallback) {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}

export default function useSidebarLayout() {
  const [preferredWidth, setPreferredWidth] = useState(() => {
    const saved = Number(savedPreference('ramancloud_sidebar_width', DEFAULT_WIDTH));
    return Number.isFinite(saved) && saved >= MIN_WIDTH
      ? Math.min(MAX_WIDTH, saved) : DEFAULT_WIDTH;
  });
  const [desktopCollapsed, setDesktopCollapsed] = useState(() => savedPreference('ramancloud_sidebar_collapsed', 'false') === 'true');
  const [viewportWidth, setViewportWidth] = useState(window.innerWidth);
  const [mobileOpen, setMobileOpen] = useState(false);
  const narrow = viewportWidth <= 760;
  const collapsed = narrow ? !mobileOpen : desktopCollapsed;
  const maxWidth = narrow ? Math.min(MAX_WIDTH, viewportWidth - 64) : Math.min(MAX_WIDTH, Math.floor(viewportWidth * 0.35));
  const width = collapsed ? 56 : Math.min(preferredWidth, maxWidth);

  useEffect(() => {
    const resize = () => setViewportWidth(window.innerWidth);
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);

  useEffect(() => { setMobileOpen(false); }, [narrow]);

  useEffect(() => {
    const timer = setTimeout(() => {
      try {
        localStorage.setItem('ramancloud_sidebar_width', String(preferredWidth));
        localStorage.setItem('ramancloud_sidebar_collapsed', String(desktopCollapsed));
      } catch { /* Navigation remains usable when storage is unavailable. */ }
    }, 150);
    return () => clearTimeout(timer);
  }, [preferredWidth, desktopCollapsed]);

  useEffect(() => {
    const frame = requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
    return () => cancelAnimationFrame(frame);
  }, [width]);

  return {
    width, collapsed, narrow, minWidth: MIN_WIDTH, maxWidth,
    overlay: narrow && mobileOpen,
    toggle: () => narrow ? setMobileOpen(value => !value) : setDesktopCollapsed(value => !value),
    closeMobile: () => setMobileOpen(false),
    resize: value => setPreferredWidth(Math.round(Math.min(maxWidth, Math.max(MIN_WIDTH, value)))),
    resetWidth: () => setPreferredWidth(DEFAULT_WIDTH),
  };
}
