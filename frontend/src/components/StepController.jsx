import { systemText, localize } from '../locale.js';
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {useAuth} from '../auth';
import {legacyAlgorithms,legacyDefaults} from './legacyAlgorithms';
import LegacyAlgorithmParameters from './LegacyAlgorithmParameters';
import { GripVertical, Scissors, Eraser, Waves, Baseline, ChevronDown, ChevronUp, Plus, X } from 'lucide-react';
import { usePreferences } from '../i18n';
import TSHIParameters from './TSHIParameters';
import { denoiseDefaults } from './tshiDefaults.mjs';
import DespikeParameters from './DespikeParameters';
import { insertDespike, canMoveStep } from '../pages/analysisWorkflow';

const STEP_TYPES = {
  cut: { icon: Scissors, labelKey: 'cut', color: 'from-emerald-500 to-teal-600' },
  despike: { icon: Eraser, labelKey: 'despike' },
  denoise: { icon: Waves, labelKey: 'denoise', color: 'from-blue-500 to-cyan-600' },
  baseline: { icon: Baseline, labelKey: 'baseline', color: 'from-purple-500 to-pink-600' },
};

const DENOISE_OPTIONS = [{value:'skip',labelKey:'skip'}];
const BASELINE_OPTIONS = [{value:'skip',labelKey:'skip'}];

export default function StepController({ steps, onChange, defaultCutRange, tshiContext, horizontal = false }) {
  const {token}=useAuth();
  const [legacyStatus,setLegacyStatus]=useState({});
  useEffect(()=>{const abort=new AbortController();axios.get(`${import.meta.env.BASE_URL.replace(/\/$/,'')}/api/legacy-algorithms`,{headers:{Authorization:`Bearer ${token}`},signal:abort.signal}).then(({data})=>setLegacyStatus(Object.fromEntries(data.algorithms.map(s=>[s.method,s])))).catch(()=>{});return()=>abort.abort();},[token]);
  const [expandedStep, setExpandedStep] = useState(null);
  const { t } = usePreferences();

  const addStep = (type) => {
    if (type === 'despike') {
      if (steps.some(step => step.type === 'despike')) return;
      const step = { id: crypto.randomUUID(), type, method: 'despike', params: { threshold: null, fwhm_threshold: 4 } };
      onChange(insertDespike(steps, step)); setExpandedStep(step.id); return;
    }
    const newStep = {
      id: crypto.randomUUID(),
      type,
      method: type === 'cut' ? 'cut' : type === 'denoise' ? 'sg' : 'airpls',
      params: type === 'cut'
        ? { start: defaultCutRange?.[0] ?? 0, end: defaultCutRange?.[1] ?? 4000 }
        : type === 'denoise'
          ? { window_size: 7, order: 3 }
          : legacyDefaults('airpls'),
    };
    onChange([...steps, newStep]);
    setExpandedStep(newStep.id);
  };

  const removeStep = (id) => {
    onChange(steps.filter(s => s.id !== id));
  };

  const updateStep = (id, updates) => {
    onChange(steps.map(s => s.id === id ? { ...s, ...updates } : s));
  };

  const moveStep = (index, direction) => {
    if (!canMoveStep(steps, index, direction)) return;
    const newSteps = [...steps];
    const target = index + direction;
    if (target < 0 || target >= steps.length) return;
    [newSteps[index], newSteps[target]] = [newSteps[target], newSteps[index]];
    onChange(newSteps);
  };

  const usedTypes = steps.map(s => s.type);

  return (
    <div className={horizontal ? "hyper-horizontal-steps space-y-3" : "space-y-3"}>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">{t('pipelineSteps')}</h3>
        <span className="text-xs text-gray-500">{steps.length} {steps.length === 1 ? t('stepSingular') : t('stepPlural')}</span>
      </div>

      {/* Step list */}
      <div className="hyper-step-grid space-y-2">
        {steps.map((step, index) => {
          const typeInfo = STEP_TYPES[step.type];
          const Icon = typeInfo.icon;
          const isExpanded = expandedStep === step.id;

          return (
            <div key={step.id} className={horizontal ? 'hyper-step-item' : `glass rounded-xl overflow-hidden border ${isExpanded ? 'border-indigo-500/30' : 'border-white/5'} transition-all duration-200`}>
              {/* Step header */}
              <div
                className="hyper-step-header flex items-center gap-2 p-3 cursor-pointer hover:bg-white/5"
                style={horizontal ? {order:index} : undefined}
                role="button" tabIndex={0} aria-expanded={isExpanded}
                onKeyDown={e=>{if(e.target===e.currentTarget && (e.key==='Enter'||e.key===' ')){e.preventDefault();setExpandedStep(isExpanded?null:step.id);}}}
                onClick={() => setExpandedStep(isExpanded ? null : step.id)}
              >
                <GripVertical className="w-3.5 h-3.5 text-gray-600 cursor-grab" />
                <span className="text-xs font-mono text-gray-500 w-5">{index + 1}</span>
                <div className={`w-7 h-7 flex items-center justify-center ${typeInfo.color ? `rounded-lg bg-gradient-to-br ${typeInfo.color}` : ''}`}>
                  <Icon className={`w-3.5 h-3.5${typeInfo.color ? ' text-white' : ''}`} />
                </div>
                <span className="text-sm font-medium text-gray-200">{t(typeInfo.labelKey)}</span>
                {step.type !== 'despike' && step.method !== 'cut' && step.method !== 'skip' && (
                  <span className="text-xs text-gray-500 ml-auto mr-1 truncate" title={legacyAlgorithms.find(s=>s.method===step.method)?.label || step.method}>
                    {legacyAlgorithms.find(s=>s.method===step.method)?.label || step.method}
                  </span>
                )}
                <div className="flex items-center gap-1 ml-auto">
                  {canMoveStep(steps, index, -1) && (
                    <button title={localize("上移步骤")} aria-label={localize("上移步骤")} onClick={(e) => { e.stopPropagation(); moveStep(index, -1); }}
                      className="p-1 hover:bg-white/10 rounded transition-colors">
                      <ChevronUp className="w-3 h-3 text-gray-400" />
                    </button>
                  )}
                  {canMoveStep(steps, index, 1) && (
                    <button title={localize("下移步骤")} aria-label={localize("下移步骤")} onClick={(e) => { e.stopPropagation(); moveStep(index, 1); }}
                      className="p-1 hover:bg-white/10 rounded transition-colors">
                      <ChevronDown className="w-3 h-3 text-gray-400" />
                    </button>
                  )}
                  <button title={localize("删除步骤")} aria-label={localize("删除步骤")} onClick={(e) => { e.stopPropagation(); removeStep(step.id); }}
                    className="p-1 hover:bg-red-500/20 rounded transition-colors">
                    <X className="w-3 h-3 text-gray-500 hover:text-red-400" />
                  </button>
                </div>
              </div>

              {/* Step params */}
              {isExpanded && (
                <div className="hyper-step-parameters px-3 pb-3 pt-1 border-t border-white/5 bg-black/20 animate-fade-in" style={horizontal ? {order:steps.length+1} : undefined}>
                  {step.type === 'despike' && <>
                    <label className="flex items-center gap-2 text-xs py-2"><input type="checkbox" checked={step.method !== 'skip'} onChange={e => {
                      const updated = { ...step, method: e.target.checked ? 'despike' : 'skip' };
                      onChange(e.target.checked ? insertDespike(steps.filter(item => item.id !== step.id), updated) : steps.map(item => item.id === step.id ? updated : item));
                    }} />{t('enableDespike')}</label>
                    <DespikeParameters params={step.params} disabled={step.method === 'skip'} onChange={params => updateStep(step.id, { params })} />
                  </>}
                  {step.type === 'cut' && (
                    <div className="space-y-2">
                      <label className="text-xs text-gray-400">{t('wavenumberRange')}</label>
                      <div className="flex gap-2">
                        <input
                          type="number"
                          value={step.params.start}
                          onChange={e => updateStep(step.id, { params: { ...step.params, start: parseFloat(e.target.value) || 0 } })}
                          className="w-full px-2 py-1.5 text-xs bg-black/30 border border-white/10 rounded text-gray-200 focus:border-indigo-500/50 focus:outline-none"
                          placeholder={t('start')}
                        />
                        <span className="text-gray-500 self-center">–</span>
                        <input
                          type="number"
                          value={step.params.end}
                          onChange={e => updateStep(step.id, { params: { ...step.params, end: parseFloat(e.target.value) || 4000 } })}
                          className="w-full px-2 py-1.5 text-xs bg-black/30 border border-white/10 rounded text-gray-200 focus:border-indigo-500/50 focus:outline-none"
                          placeholder={t('end')}
                        />
                      </div>
                    </div>
                  )}

                  {step.type === 'denoise' && (
                    <div className="space-y-2">
                      <label className="text-xs text-gray-400">{t('method')}</label>
                      <select
                        value={step.method}
                        aria-label={localize("降噪算法")}
                        onChange={e => updateStep(step.id, { method: e.target.value, params: denoiseDefaults(e.target.value, tshiContext) })}
                        className="w-full px-2 py-1.5 text-xs bg-black/30 border border-white/10 rounded text-gray-200 focus:border-indigo-500/50 focus:outline-none"
                      >
                        {legacyAlgorithms.filter(s=>s.type==='denoise').map(s=><option key={s.method} value={s.method} disabled={!legacyStatus[s.method]?.available}>{systemText(s.label)}{legacyStatus[s.method]?.available?'':localize('（需配置环境/权重）')}</option>)}
                        {DENOISE_OPTIONS.map(o => (
                          <option key={o.value} value={o.value}>{systemText(o.labelKey ? t(o.labelKey) : o.label)}</option>
                        ))}
                        {(tshiContext?.isImaging || step.method === 'tshi') && <option value="tshi" disabled={!tshiContext?.isImaging}>TSHI / IIALRMA</option>}
                      </select>
                      {step.method === 'tshi' && <TSHIParameters params={step.params}
                        bm3dAvailable={tshiContext?.bm3dAvailable} onChange={params => updateStep(step.id, { params })} />}
                      <LegacyAlgorithmParameters method={step.method} params={step.params} onChange={params=>updateStep(step.id,{params})}/>
                      {!legacyAlgorithms.some(s=>s.method===step.method) && step.method === 'sg' && (
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <label className="text-[10px] text-gray-500">{t('window')}</label>
                            <input type="number" value={step.params.window_size}
                              onChange={e => updateStep(step.id, { params: { ...step.params, window_size: parseInt(e.target.value) || 7 } })}
                              className="w-full px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200 focus:border-indigo-500/50 focus:outline-none" />
                          </div>
                          <div>
                            <label className="text-[10px] text-gray-500">{t('order')}</label>
                            <input type="number" value={step.params.order}
                              onChange={e => updateStep(step.id, { params: { ...step.params, order: parseInt(e.target.value) || 3 } })}
                              className="w-full px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200 focus:border-indigo-500/50 focus:outline-none" />
                          </div>
                        </div>
                      )}
                      {!legacyAlgorithms.some(s=>s.method===step.method) && step.method === 'peer' && (
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <label className="text-[10px] text-gray-500">{t('loops')}</label>
                            <input type="number" value={step.params.loops || 3}
                              onChange={e => updateStep(step.id, { params: { ...step.params, loops: parseInt(e.target.value) || 3 } })}
                              className="w-full px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200 focus:border-indigo-500/50 focus:outline-none" />
                          </div>
                          <div>
                            <label className="text-[10px] text-gray-500">{t('peakSeek')}</label>
                            <input type="number" value={step.params.half_k_threshold || 2}
                              onChange={e => updateStep(step.id, { params: { ...step.params, half_k_threshold: parseInt(e.target.value) || 2 } })}
                              className="w-full px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200 focus:border-indigo-500/50 focus:outline-none" />
                          </div>
                        </div>
                      )}
                      {!legacyAlgorithms.some(s=>s.method===step.method) && step.method === 'wtd' && (
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <label className="text-[10px] text-gray-500">{t('wavelet')}</label>
                            <select value={step.params.wavelet || 'db3'}
                              onChange={e => updateStep(step.id, { params: { ...step.params, wavelet: e.target.value } })}
                              className="w-full px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200 focus:border-indigo-500/50 focus:outline-none">
                              {['db1','db2','db3','db4','db5','db6','db7','db8'].map(w => (
                                <option key={w} value={w}>{w}</option>
                              ))}
                            </select>
                          </div>
                          <div>
                            <label className="text-[10px] text-gray-500">{t('level')}</label>
                            <input type="number" value={step.params.level || 3}
                              onChange={e => updateStep(step.id, { params: { ...step.params, level: parseInt(e.target.value) || 3 } })}
                              className="w-full px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200 focus:border-indigo-500/50 focus:outline-none" />
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {step.type === 'baseline' && (
                    <div className="space-y-2">
                      <label className="text-xs text-gray-400">{t('method')}</label>
                      <select
                        value={step.method}
                        onChange={e => updateStep(step.id, { method: e.target.value, params:legacyDefaults(e.target.value)|| (e.target.value==='airpls'?{lam:1e7,diff_order:3}:e.target.value==='snip'?{half_window:40}:e.target.value==='imodpoly'?{poly_order:3}:{}) })}
                        className="w-full px-2 py-1.5 text-xs bg-black/30 border border-white/10 rounded text-gray-200 focus:border-indigo-500/50 focus:outline-none"
                      >
                        {legacyAlgorithms.filter(s=>s.type==='baseline').map(s=><option key={s.method} value={s.method} disabled={!legacyStatus[s.method]?.available}>{systemText(s.label)}{legacyStatus[s.method]?.available?'':localize('（需配置环境/权重）')}</option>)}
                        {BASELINE_OPTIONS.map(o => (
                          <option key={o.value} value={o.value}>{systemText(o.labelKey ? t(o.labelKey) : o.label)}</option>
                        ))}
                      </select>
                      <LegacyAlgorithmParameters method={step.method} params={step.params} onChange={params=>updateStep(step.id,{params})}/>
                      {!legacyAlgorithms.some(s=>s.method===step.method) && step.method === 'airpls' && (
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <label className="text-[10px] text-gray-500">{t('lambda')}</label>
                            <select value={step.params.lam || 1e7}
                              onChange={e => updateStep(step.id, { params: { ...step.params, lam: parseFloat(e.target.value) } })}
                              className="w-full px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200 focus:border-indigo-500/50 focus:outline-none">
                              {[1e4, 1e5, 1e6, 1e7, 1e8, 1e9, 1e10].map(v => (
                                <option key={v} value={v}>{v.toExponential(0)}</option>
                              ))}
                            </select>
                          </div>
                          <div>
                            <label className="text-[10px] text-gray-500">{t('diffOrder')}</label>
                            <input type="number" value={step.params.diff_order || 3}
                              onChange={e => updateStep(step.id, { params: { ...step.params, diff_order: parseInt(e.target.value) || 3 } })}
                              className="w-full px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200 focus:border-indigo-500/50 focus:outline-none" />
                          </div>
                        </div>
                      )}
                      {!legacyAlgorithms.some(s=>s.method===step.method) && step.method === 'aabs' && (
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <label className="text-[10px] text-gray-500">Ln</label>
                            <input type="number" value={step.params.Ln || 6}
                              onChange={e => updateStep(step.id, { params: { ...step.params, Ln: parseInt(e.target.value) || 6 } })}
                              className="w-full px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200" />
                          </div>
                          <div>
                            <label className="text-[10px] text-gray-500">Lb</label>
                            <input type="number" value={step.params.Lb || 140}
                              onChange={e => updateStep(step.id, { params: { ...step.params, Lb: parseInt(e.target.value) || 140 } })}
                              className="w-full px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200" />
                          </div>
                        </div>
                      )}
                      {!legacyAlgorithms.some(s=>s.method===step.method) && step.method === 'imodpoly' && (
                        <div>
                          <label className="text-[10px] text-gray-500">{t('polyOrder')}</label>
                          <input type="number" value={step.params.poly_order || 3}
                            onChange={e => updateStep(step.id, { params: { ...step.params, poly_order: parseInt(e.target.value) || 3 } })}
                            className="w-full px-2 py-1 text-xs bg-black/30 border border-white/10 rounded text-gray-200" />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {steps.length === 0 && (
          <div className="text-center py-6 text-gray-600 text-sm">
            {t('addStepsHint')}
          </div>
        )}
      </div>

      {/* Add step buttons */}
      <div className="flex gap-2">
        {Object.entries(STEP_TYPES).map(([type, info]) => {
          const Icon = info.icon;
          return (
            <button
              key={type}
              disabled={type === 'despike' && usedTypes.includes('despike')}
              onClick={() => addStep(type)}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-medium transition-all duration-200 bg-white/5 hover:bg-white/10 text-gray-400 hover:text-gray-200 border border-white/5 hover:border-white/10`}
            >
              <Icon className="w-3 h-3" />
              {t(info.labelKey)}
            </button>
          );
        })}
      </div>
    </div>
  );
}
