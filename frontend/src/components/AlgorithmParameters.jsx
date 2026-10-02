import React from 'react';
import { algorithms, algorithmDefaults } from '../data/algorithms';
import { usePreferences } from '../i18n';

export default function AlgorithmParameters({ step, update, allowBatch = false }) {
  const { language, t } = usePreferences();
  const isZh = language === 'zh';
  const selected = algorithms.find(item => item.id === step.method);
  const options = algorithms.filter(item => item.type === step.type && (!item.batchOnly || allowBatch));
  return <div className="space-y-3">
    <label className="block text-xs text-gray-400">{t('method')}
      <select aria-label={t('method')} value={step.method} onChange={event => update({ method: event.target.value, params: algorithmDefaults(event.target.value) })}
        className="block w-full px-2 py-1.5 mt-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200">
        {options.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
        {step.type !== 'baseline' && <option value="skip">{t('skip')}</option>}
      </select>
    </label>
    <div className="grid grid-cols-2 gap-2">
      {selected?.fields.map(field => <label key={field.key} className="block min-w-0 text-xs text-gray-500">
        {isZh ? field.zh : field.label}
        {field.options ? <select aria-label={isZh ? field.zh : field.label} value={step.params[field.key] ?? field.value}
          onChange={event => update({ params: { ...step.params, [field.key]: event.target.value } })}
          className="block w-full px-2 py-1.5 mt-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200">
          {field.options.map(value => <option key={value}>{value}</option>)}
        </select> : <input type="number" aria-label={isZh ? field.zh : field.label} min={field.min} max={field.max} step={field.step}
          value={step.params[field.key] ?? field.value} onChange={event => update({ params: { ...step.params, [field.key]: event.target.value === '' ? '' : Number(event.target.value) } })}
          className="block w-full px-2 py-1.5 mt-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200" />}
      </label>)}
    </div>
    {!!selected?.fields.length && <details className="text-xs text-gray-500">
      <summary className="cursor-pointer text-indigo-400 py-1">{isZh ? '参数说明' : 'Parameter guide'}</summary>
      <dl className="space-y-2 mt-2">
        {selected.fields.map(field => <div key={field.key}><dt className="font-medium">{isZh ? field.zh : field.label}</dt><dd className="leading-relaxed">{isZh ? field.helpZh : field.help}</dd></div>)}
      </dl>
    </details>}
  </div>;
}
