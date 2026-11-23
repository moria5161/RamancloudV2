import React from 'react';
import {legacyAlgorithms} from './legacyAlgorithms';
import {systemText, localize} from '../locale.js';
import {usePreferences} from '../i18n';
export default function LegacyAlgorithmParameters({method,params,onChange}) {
  usePreferences();
  const spec=legacyAlgorithms.find(s=>s.method===method);
  if(!spec)return null;
  return <div className="space-y-2">{Object.entries(spec.params).map(([key,rule])=><label key={key} className="block text-xs text-gray-400">{systemText(rule.label)}{rule.options?<select aria-label={`${systemText(spec.label)} ${systemText(rule.label)}`} value={params[key]??rule.default} onChange={e=>onChange({...params,[key]:e.target.value})}>{rule.options.map(value=><option key={value}>{value}</option>)}</select>:<input aria-label={`${systemText(spec.label)} ${systemText(rule.label)}`} className="w-full px-2 py-1 text-xs bg-black/30 border border-white/10 rounded" type="number" min={rule.min} max={rule.max} step={rule.integer?1:'any'} value={params[key]??rule.default} onChange={e=>onChange({...params,[key]:Number(e.target.value)})}/>}</label>)}{!Object.keys(spec.params).length&&<small>{localize('使用模型预设参数。')}</small>}</div>;
}
