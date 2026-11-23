import { useEffect, useRef } from 'react';
import axios from 'axios';
import { localize } from '../locale.js';

// Page-owned values only. Hidden cached pages cannot answer another module's request.
export function useQAExecutionInput(module, inputs, files = [], locked = false) {
  const ref = useRef(); ref.current = { module, inputs, files, locked };
  useEffect(() => { document.dispatchEvent(new Event('qa-execution-input-changed')); });
  useEffect(() => {
    const read = event => { if (event.detail.module === module) event.detail.value = ref.current; };
    document.addEventListener('qa-read-execution-input', read);
    return () => document.removeEventListener('qa-read-execution-input', read);
  }, [module]);
}

export function executionInput(path) {
  const module = path.split('/').filter(Boolean).at(-1);
  const detail = { module, value: null };
  document.dispatchEvent(new CustomEvent('qa-read-execution-input', { detail }));
  return detail.value;
}

export async function executionKey(context) {
  const normalize = value => Array.isArray(value) ? value.map(normalize) : value && typeof value === 'object'
    ? Object.fromEntries(Object.keys(value).sort().map(k => [k, normalize(value[k])])) : value;
  const bytes = new TextEncoder().encode(JSON.stringify(normalize({ module: context.module, inputs: context.inputs,
    files: context.files.map(file => ({ name: file.name, size: file.size, lastModified: file.lastModified })) })));
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(b => b.toString(16).padStart(2,'0')).join('');
}

export async function checkPlanContext(context, plan) {
  if (!context) throw new Error(localize('当前页面没有可运行的输入，请返回方案来源页面。'));
  if (context.locked) throw new Error(localize('当前模块正在处理或导入，请等待完成。'));
  if (await executionKey(context) !== plan.context_key) {
    throw new Error(localize('当前数据、版本或参数已变化，请根据当前输入重新生成方案。'));
  }
}

export async function executeQAPlan(base, plan, headers, { units = false, sharing = false, signal } = {}) {
  const { data } = await axios.post(base + '/qa-assistant/plans/' + plan.id + '/execute', {
    revision: plan.revision, context_key: plan.context_key, confirm_units: units, confirm_sharing: sharing,
  }, { headers, signal, timeout: 60000 });
  return data;
}
