import React, { useEffect, useRef, useState } from 'react';
import { PanelRightClose, PanelRightOpen } from 'lucide-react';
import { usePreferences } from '../i18n';

export default function ControlDock({ children }) {
  const { t } = usePreferences();
  const [open, setOpen] = useState(() => window.innerWidth >= 1100);
  const ref = useRef(null);
  useEffect(() => {
    const narrow = window.matchMedia('(max-width: 760px)');
    const resize = () => { if (narrow.matches) setOpen(false); };
    narrow.addEventListener('change', resize);
    return () => narrow.removeEventListener('change', resize);
  }, []);
  useEffect(() => {
    if (!open) return;
    const dismiss = event => {
      if (window.innerWidth <= 760 && !ref.current?.contains(event.target)) setOpen(false);
    };
    const escape = event => {
      if (event.key === 'Escape' && !event.target.closest?.('dialog')) setOpen(false);
    };
    document.addEventListener('pointerdown', dismiss, true);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', dismiss, true); document.removeEventListener('keydown', escape); };
  }, [open]);
  useEffect(() => {
    const frame = requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
    return () => cancelAnimationFrame(frame);
  }, [open]);
  return (
    <aside ref={ref} className={`control-dock shrink-0 relative ${open ? 'is-open' : ''}`}>
      <button className="control-dock-toggle" onClick={() => setOpen(previous => !previous)} title={t(open ? 'closeControls' : 'openControls')} aria-label={t(open ? 'closeControls' : 'openControls')} aria-expanded={open}>
        {open ? <PanelRightClose className="w-4 h-4" /> : <PanelRightOpen className="w-4 h-4" />}
      </button>
      <div hidden={!open} className="h-full">{children}</div>
    </aside>
  );
}
