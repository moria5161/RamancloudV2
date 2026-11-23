import React from 'react';
import { usePreferences } from '../i18n';
import { localize, systemText, systemValue } from '../locale.js';
import { legacyAlgorithms } from './legacyAlgorithms';

const methods = {
  despike: 'Despike',
  tshi: 'TSHI / IIALRMA',
  voigt: 'Voigt',
  peaknet: 'PeakNet',
  vib2mol: 'Vib2Mol',
  cut: '波段裁剪',
};

const labels = {
  despike: '去鬼峰',
  denoise: '降噪',
  denoising: '降噪',
  baseline: '基线校正',
  baseline_correction: '基线校正',
  cut: '波段裁剪',
  crop: '波段裁剪',
  start: '起始波数',
  end: '终止波数',
  points: '数据点数',
  top_k: '候选数量',
  rerank: '光谱匹配重排',
  formula: '分子式',
  preprocessing_mode: '输入预处理',
  engine: '生成引擎',
  threshold: '阈值',
  lam: '平滑系数',
  diff_order: '差分阶数',
  window_size: '窗口点数',
  poly_order: '多项式阶数',
  fwhm_threshold: '半峰宽阈值',
  repair_policy: '修复规则',
  interpolation: '插值方式',
  implementation: '算法版本',
  unit_confirmed: '已确认拉曼位移单位',
  baseline_confirmed: '已确认基线校正',
  baseline_evidence: '基线校正依据',
  peer_window: 'PEER 窗口大小',
  peer_iterations: 'PEER 迭代次数',
  baseline_lambda: '基线平滑系数',
  baseline_iterations: '基线最大迭代次数',
  iterations: '实际迭代次数',
  removed_offset: '扣除的强度偏移',
  normalization_scale: '归一化系数',
  epochs: '训练轮次',
  samples_per_epoch: '每轮样本数',
  batch_size: '训练批大小',
  rf_samples: '随机森林训练样本数',
  trees: '随机森林树数',
  device: '运行设备',
};

const resolvedKeys = ['threshold', 'fwhm_threshold', 'repair_policy', 'interpolation', 'center_wavenumber', 'selected_range',
  'selected_bands', 'actual_count', 'windowsize', 'effective_rank', 'selected_components',
  'spectral_threshold', 'bm3d_enabled', 'bm3d_sigma'];
const optionLabels = {auto:'自动',prepared:'使用当前处理结果',saved_processing_steps:'已保存的处理步骤',user_confirmation:'用户确认'};
const algorithmSpec = method => legacyAlgorithms.find(item => item.method === method?.replace(/^v2_/, ''));

export const recordStepLabel = value => localize(labels[value] || String(value ?? '—'));

export function recordMethodLabel(method, type) {
  const spec = algorithmSpec(method);
  return localize(spec?.label || methods[method] || method || (type === 'cut' ? methods.cut : '—'));
}

function parameterValue(key, value, method) {
  if (value == null) return method === 'despike' && key === 'threshold' ? localize('自动') : '—';
  if (typeof value === 'boolean') return localize(value ? '启用' : '关闭');
  if (typeof value === 'object') {
    return <pre className="dw-parameter-value">{JSON.stringify(systemValue(value), null, Array.isArray(value) ? 0 : 2)}</pre>;
  }
  return systemText(Object.hasOwn(optionLabels,value) ? optionLabels[value] : String(value));
}

export function RecordParameters({ values, method }) {
  const { language } = usePreferences();
  const entries = Object.entries(values || {});
  if (!entries.length) return <p className="dw-muted">{language === 'zh' ? '此步骤无单独保存的参数。' : 'No parameters were saved for this step.'}</p>;
  const catalogParams = algorithmSpec(method)?.params;
  return <dl>{entries.map(([key, value]) => <React.Fragment key={key}>
    <dt>{catalogParams?.[key]?.label ? localize(catalogParams[key].label) : recordStepLabel(key)}</dt>
    <dd>{parameterValue(key,value,method)}</dd>
  </React.Fragment>)}</dl>;
}

export default function AnalysisRecordSteps({ steps = [], history = [] }) {
  const { language } = usePreferences();
  const txt = (zh, en) => language === 'zh' ? zh : en;
  const entries = history.filter(entry => entry.step || entry.type);
  const records = entries.length ? entries : steps;
  if (!records.length) return <p className="dw-muted">{txt('此记录没有保存处理步骤。', 'This record has no saved processing steps.')}</p>;
  return records.map((record, index) => {
    const step = record.step || record;
    const method = recordMethodLabel(step.method, step.type);
    const resolved = Object.fromEntries(resolvedKeys.filter(key => record.details?.[key] != null)
      .map(key => [key, record.details[key]]));
    const skipped = step.enabled === false || step.method === 'skip' || record.status === 'skipped';
    return <section className="dw-step" key={index}>
      <h4>{index + 1}. {recordStepLabel(step.type)}{step.method !== 'skip' && method !== recordStepLabel(step.type) && ` · ${method}`}{skipped && ` · ${localize('已跳过')}`}</h4>
      <RecordParameters values={record.range ? {start:record.range[0],end:record.range[1]} : step.params} method={step.method} />
      {Object.keys(resolved).length > 0 && <details>
        <summary>{txt('本次运行确定的参数', 'Parameters resolved during execution')}</summary>
        <RecordParameters values={resolved} method={step.method} />
      </details>}
    </section>;
  });
}
