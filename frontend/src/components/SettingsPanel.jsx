import React, { useEffect, useRef, useState } from 'react';
import { Check, Languages, Moon, Settings, Sun } from 'lucide-react';
import { usePreferences } from '../i18n';

export default function SettingsPanel() {
  const [open, setOpen] = useState(false);
  const { language, setLanguage, theme, setTheme, t } = usePreferences();
  const dockRef = useRef(null);
  const triggerRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const dismissOutside = event => {
      if (!dockRef.current?.contains(event.target)) setOpen(false);
    };
    const dismissOnEscape = event => {
      if (event.key === 'Escape') {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener('pointerdown', dismissOutside, true);
    document.addEventListener('keydown', dismissOnEscape);
    return () => {
      document.removeEventListener('pointerdown', dismissOutside, true);
      document.removeEventListener('keydown', dismissOnEscape);
    };
  }, [open]);

  return (
    <div ref={dockRef} className="settings-dock">
      {open && (
        <div id="settings-popover" className="settings-popover glass rounded-xl border border-white/5 p-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-gray-200 mb-4">
            <Settings className="w-4 h-4 text-indigo-400" />
            {t('settings')}
          </div>
          <div className="space-y-4">
            <div>
              <div className="flex items-center gap-2 text-xs text-gray-500 mb-2">
                <Languages className="w-3.5 h-3.5" />
                {t('language')}
              </div>
              <div className="segmented-control">
                {[
                  ['en', t('english')],
                  ['zh', t('chinese')],
                ].map(([value, label]) => (
                  <button key={value} onClick={() => setLanguage(value)} className={language === value ? 'is-active' : ''}>
                    {label}
                    {language === value && <Check className="w-3 h-3" />}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2 text-xs text-gray-500 mb-2">
                {theme === 'dark' ? <Moon className="w-3.5 h-3.5" /> : <Sun className="w-3.5 h-3.5" />}
                {t('appearance')}
              </div>
              <div className="segmented-control">
                {[
                  ['light', t('light'), Sun],
                  ['dark', t('dark'), Moon],
                ].map(([value, label, Icon]) => (
                  <button key={value} onClick={() => setTheme(value)} className={theme === value ? 'is-active' : ''}>
                    <Icon className="w-3.5 h-3.5" />
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
      <button ref={triggerRef} className="settings-trigger glass" onClick={() => setOpen((value) => !value)} aria-label={t('settings')} aria-expanded={open} aria-controls="settings-popover">
        <Settings className="w-4 h-4" />
      </button>
    </div>
  );
}
