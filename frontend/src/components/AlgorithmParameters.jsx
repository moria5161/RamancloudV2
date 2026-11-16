import React, { useState } from 'react';
import { Minus, Plus } from 'lucide-react';
import { algorithms, algorithmDefaults, stepLogarithmicParameter } from '../data/algorithms';
import { usePreferences } from '../i18n';

function LogarithmicParameter({ field, value, onChange, isZh }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const displayValue = Number.isFinite(value) ? value.toExponential() : value;
  const label = isZh ? field.zh : field.label;
  const decrease = `${label}: ${isZh ? '减小一个数量级' : 'Decrease by one order of magnitude'} (÷10)`;
  const increase = `${label}: ${isZh ? '增大一个数量级' : 'Increase by one order of magnitude'} (×10)`;
  const adjust = direction => {
    const next = stepLogarithmicParameter(field, value, direction);
    setDraft(next.toExponential());
    onChange(next);
  };
  return <div className="flex items-center gap-1 mt-1">
    <button type="button" aria-label={decrease} title={decrease} disabled={value !== '' && value <= field.min}
      onClick={event => { event.preventDefault(); adjust(-1); }}
      className="shrink-0 w-6 h-7 flex items-center justify-center rounded text-gray-400 hover:bg-white/10 disabled:opacity-30">
      <Minus className="w-3 h-3" />
    </button>
    <input type="number" aria-label={label} min={field.min} max={field.max} step="any"
      value={editing ? draft : displayValue}
      onFocus={() => { setDraft(displayValue); setEditing(true); }}
      onBlur={() => setEditing(false)}
      onChange={event => {
        setDraft(event.target.value);
        onChange(event.target.value === '' ? '' : Number(event.target.value));
      }}
      onKeyDown={event => {
        if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
          event.preventDefault();
          adjust(event.key === 'ArrowUp' ? 1 : -1);
        }
      }}
      className="logarithmic-parameter block min-w-0 w-full px-2 py-1.5 text-xs bg-black/30 border border-white/10 rounded text-gray-200" />
    <button type="button" aria-label={increase} title={increase} disabled={value !== '' && value >= field.max}
      onClick={event => { event.preventDefault(); adjust(1); }}
      className="shrink-0 w-6 h-7 flex items-center justify-center rounded text-gray-400 hover:bg-white/10 disabled:opacity-30">
      <Plus className="w-3 h-3" />
    </button>
  </div>;
}

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
        </select> : field.scale === 'log' ? <LogarithmicParameter field={field} value={step.params[field.key] ?? field.value} isZh={isZh}
          onChange={value => update({ params: { ...step.params, [field.key]: value } })} /> : <input type="number" aria-label={isZh ? field.zh : field.label} min={field.min} max={field.max} step={field.step}
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
