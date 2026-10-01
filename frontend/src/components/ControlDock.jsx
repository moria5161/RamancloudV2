import React, { useEffect, useState } from 'react';
import { PanelRightClose, PanelRightOpen } from 'lucide-react';
import { usePreferences } from '../i18n';

export default function ControlDock({ children }) {
  const { t } = usePreferences();
  const [open, setOpen] = useState(() => window.innerWidth >= 1100);
  useEffect(() => {
    const frame = requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
    return () => cancelAnimationFrame(frame);
  }, [open]);
  return (
    <aside className={`control-dock shrink-0 relative ${open ? 'is-open' : ''}`}>
      <button className="control-dock-toggle" onClick={() => setOpen(previous => !previous)} title={t(open ? 'closeControls' : 'openControls')} aria-label={t(open ? 'closeControls' : 'openControls')} aria-expanded={open}>
        {open ? <PanelRightClose className="w-4 h-4" /> : <PanelRightOpen className="w-4 h-4" />}
      </button>
      <div hidden={!open} className="h-full">{children}</div>
    </aside>
  );
}
