import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown, X } from 'lucide-react';
import { usePreferences } from '../i18n';

export default function UploadedSpectrumPicker({ id, spectra, selected, onChange, onRemove, busy }) {
  const { t, language } = usePreferences();
  const [open, setOpen] = useState(false);
  const container = useRef(null);
  const trigger = useRef(null);

  useEffect(() => {
    if (busy || !spectra.length) setOpen(false);
  }, [busy, spectra.length]);

  useEffect(() => {
    if (!open) return;
    const outside = event => {
      if (!container.current?.contains(event.target)) setOpen(false);
    };
    const escape = event => {
      if (event.key === 'Escape') {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
    };
  }, [open]);

  return (
    <div ref={container} className="relative">
      <button id={id} ref={trigger} type="button" disabled={busy}
        aria-expanded={open} aria-controls={`${id}-files`}
        onClick={() => setOpen(value => !value)}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-xs bg-black/30 border border-white/10 rounded-lg text-gray-200">
        <span className="min-w-0 flex-1 truncate text-left">{spectra[selected]?.filename}</span>
        <ChevronDown className="w-3.5 h-3.5 shrink-0" />
      </button>
      {open && <div id={`${id}-files`} role="group" aria-label={t('uploadedSpectrum')}
        className="absolute top-full left-0 right-0 z-50 mt-1 max-h-60 overflow-y-auto rounded-lg border border-white/10 shadow-lg"
        style={{ background: 'var(--rc-surface-solid)', color: 'var(--rc-text)' }}>
        {spectra.map((spectrum, index) => {
          const removeLabel = `${language === 'zh' ? '删除光谱' : 'Remove spectrum'}: ${spectrum.filename}`;
          return (
            <div key={index} className={`flex items-center gap-1 ${index === selected ? 'bg-blue-500/15' : ''}`}>
              <button type="button" disabled={busy} aria-pressed={index === selected}
                title={spectrum.filename}
                onClick={() => { onChange(index); setOpen(false); trigger.current?.focus(); }}
                className="min-w-0 flex-1 truncate px-2.5 py-2 text-left text-xs hover:bg-blue-500/10">
                {spectrum.filename}
              </button>
              {onRemove && <button type="button" disabled={busy}
                title={removeLabel} aria-label={removeLabel}
                onClick={() => { onRemove(index); trigger.current?.focus(); }}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg hover:bg-red-500/10 hover:text-red-500">
                <X className="w-3.5 h-3.5" />
              </button>}
            </div>
          );
        })}
      </div>}
    </div>
  );
}
