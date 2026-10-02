import React, { useState } from 'react';
import { GripVertical, Scissors, Waves, Baseline, ChevronDown, ChevronUp, Plus, X } from 'lucide-react';
import { usePreferences } from '../i18n';
import { DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors } from '@dnd-kit/core';
import { SortableContext, useSortable, verticalListSortingStrategy, sortableKeyboardCoordinates, arrayMove } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import AlgorithmParameters from './AlgorithmParameters';
import { algorithms, algorithmDefaults } from '../data/algorithms';

function SortableStep({ id, children }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  return (
    <div ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition, position: 'relative', zIndex: isDragging ? 2 : undefined, opacity: isDragging ? 0.8 : 1 }}>
      {children({ attributes, listeners })}
    </div>
  );
}

function stepSummary(step, t, language) {
  if (step.type === 'cut') return `${step.params.start} - ${step.params.end} cm⁻¹`;
  if (step.method === 'sg') return `SG · ${t('window')} ${step.params.window_size} · ${t('order')} ${step.params.order}`;
  if (step.method === 'wtd') return `WTD · ${step.params.wavelet || 'db3'} · ${t('level')} ${step.params.level || 3}`;
  if (step.method === 'skip') return t('skip');
  const fields = algorithms.find(item => item.id === step.method)?.fields || [];
  return `${step.method} · ${Object.entries(step.params).map(([key, value]) => {
    const field = fields.find(item => item.key === key);
    return `${field ? (language === 'zh' ? field.zh : field.label) : key} ${typeof value === 'number' && value >= 10000 ? value.toExponential(0) : value}`;
  }).join(' · ')}`;
}

const STEP_TYPES = {
  cut: { icon: Scissors, labelKey: 'cut', color: 'from-emerald-500 to-teal-600' },
  denoise: { icon: Waves, labelKey: 'denoise', color: 'from-blue-500 to-cyan-600' },
  baseline: { icon: Baseline, labelKey: 'baseline', color: 'from-purple-500 to-pink-600' },
};


export default function StepController({ steps, onChange, defaultCutRange, allowBatch = false }) {
  const [expandedStep, setExpandedStep] = useState(null);
  const { t, language } = usePreferences();
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const addStep = (type) => {
    const newStep = {
      id: crypto.randomUUID(),
      type,
      method: type === 'cut' ? 'cut' : type === 'denoise' ? 'sg' : 'airpls',
      params: type === 'cut'
        ? { start: defaultCutRange?.[0] ?? 0, end: defaultCutRange?.[1] ?? 4000 }
        : algorithmDefaults(type === 'denoise' ? 'sg' : 'airpls'),
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
    const newSteps = [...steps];
    const target = index + direction;
    if (target < 0 || target >= steps.length) return;
    [newSteps[index], newSteps[target]] = [newSteps[target], newSteps[index]];
    onChange(newSteps);
  };

  const usedTypes = steps.map(s => s.type);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">{t('pipelineSteps')}</h3>
        <span className="text-xs text-gray-500">{steps.length} {steps.length === 1 ? t('stepSingular') : t('stepPlural')}</span>
      </div>

      {/* Step list */}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={({ active, over }) => {
        if (over && active.id !== over.id) onChange(arrayMove(steps, steps.findIndex(s => s.id === active.id), steps.findIndex(s => s.id === over.id)));
      }}>
      <SortableContext items={steps.map(step => step.id)} strategy={verticalListSortingStrategy}>
      <div className="space-y-2">
        {steps.map((step, index) => {
          const typeInfo = STEP_TYPES[step.type];
          const Icon = typeInfo.icon;
          const isExpanded = expandedStep === step.id;

          return (
            <SortableStep key={step.id} id={step.id}>{({ attributes, listeners }) => (
            <div className={`glass rounded-lg overflow-hidden border ${isExpanded ? 'border-indigo-500/30' : 'border-white/5'} transition-all duration-200`}>
              {/* Step header */}
              <div
                className="flex items-center gap-2 p-3 cursor-pointer hover:bg-white/5"
                onClick={() => setExpandedStep(isExpanded ? null : step.id)}
                role="button" tabIndex={0} aria-expanded={isExpanded}
                onKeyDown={event => { if (event.target === event.currentTarget && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); setExpandedStep(isExpanded ? null : step.id); } }}
              >
                <button {...attributes} {...listeners} title={t('reorderStep')} aria-label={t('reorderStep')} onClick={event => event.stopPropagation()} className="cursor-grab touch-none p-1 shrink-0">
                  <GripVertical className="w-3.5 h-3.5 text-gray-600" />
                </button>
                <span className="text-xs font-mono text-gray-500 w-5">{index + 1}</span>
                <div className={`w-7 h-7 rounded-lg bg-gradient-to-br ${typeInfo.color} flex items-center justify-center`}>
                  <Icon className="w-3.5 h-3.5 text-white" />
                </div>
                <span className="text-sm font-medium text-gray-200">{t(typeInfo.labelKey)}</span>
                {step.method !== 'cut' && step.method !== 'skip' && (
                  <span className="text-xs text-gray-500 ml-auto mr-1">
                    {step.method}
                  </span>
                )}
                <div className="flex items-center gap-1 ml-auto">
                  {index > 0 && (
                    <button title={t('moveUp')} aria-label={t('moveUp')} onClick={(e) => { e.stopPropagation(); moveStep(index, -1); }}
                      className="p-1 hover:bg-white/10 rounded transition-colors">
                      <ChevronUp className="w-3 h-3 text-gray-400" />
                    </button>
                  )}
                  {index < steps.length - 1 && (
                    <button title={t('moveDown')} aria-label={t('moveDown')} onClick={(e) => { e.stopPropagation(); moveStep(index, 1); }}
                      className="p-1 hover:bg-white/10 rounded transition-colors">
                      <ChevronDown className="w-3 h-3 text-gray-400" />
                    </button>
                  )}
                  <button title={t('removeStep')} aria-label={t('removeStep')} onClick={(e) => { e.stopPropagation(); removeStep(step.id); }}
                    className="p-1 hover:bg-red-500/20 rounded transition-colors">
                    <X className="w-3 h-3 text-gray-500 hover:text-red-400" />
                  </button>
                </div>
              </div>
              {!isExpanded && <p className="step-summary px-3 pb-3 text-xs text-gray-500">{stepSummary(step, t, language)}</p>}

              {/* Step params */}
              {isExpanded && (
                <div className="px-3 pb-3 pt-1 border-t border-white/5 bg-black/20 animate-fade-in">
                  {step.type === 'cut' && (
                    <div className="space-y-2">
                      <label className="text-xs text-gray-400">{t('wavenumberRange')}</label>
                      <div className="flex gap-2">
                        <input
                          type="number"
                          value={step.params.start}
                          onChange={e => updateStep(step.id, { params: { ...step.params, start: e.target.value === '' ? '' : Number(e.target.value) } })}
                          className="w-full px-2 py-1.5 text-xs bg-black/30 border border-white/10 rounded text-gray-200 focus:border-indigo-500/50 focus:outline-none"
                          placeholder={t('start')}
                        />
                        <span className="text-gray-500 self-center">–</span>
                        <input
                          type="number"
                          value={step.params.end}
                          onChange={e => updateStep(step.id, { params: { ...step.params, end: e.target.value === '' ? '' : Number(e.target.value) } })}
                          className="w-full px-2 py-1.5 text-xs bg-black/30 border border-white/10 rounded text-gray-200 focus:border-indigo-500/50 focus:outline-none"
                          placeholder={t('end')}
                        />
                      </div>
                    </div>
                  )}

                  {step.type !== 'cut' && <AlgorithmParameters step={step} allowBatch={allowBatch} update={updates => updateStep(step.id, updates)} />}
                </div>
              )}
            </div>
            )}</SortableStep>
          );
        })}

        {steps.length === 0 && (
          <div className="text-center py-6 text-gray-600 text-sm">
            {t('addStepsHint')}
          </div>
        )}
      </div>
      </SortableContext>
      </DndContext>

      {/* Add step buttons */}
      <div className="flex gap-2">
        {Object.entries(STEP_TYPES).map(([type, info]) => {
          const Icon = info.icon;
          return (
            <button
              key={type}
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
