import { systemText, localize } from '../locale.js';
import { usePreferences } from '../i18n';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { checkPlanContext, executeQAPlan } from './qaExecution';
import './QAPlanCard.css';

const ACTIVE = ['queued','running','stopping'];
const STEP_TYPES = {cut:'波数裁剪',despike:'去鬼峰',denoise:'降噪',baseline:'基线校正'};
const STATUS = { draft:'待运行',queued:'排队中',running:'执行中',stopping:'等待安全停止',completed:'已完成',failed:'失败',cancelled:'已停止',interrupted:'已中断',superseded:'已被新方案替代',discarded:'草案已撤销' };
const FIELD = { steps:'处理步骤',top_k:'候选数量',preprocessing_mode:'匹配前预处理',engine:'生成引擎',formula:'分子式约束',rerank:'候选重排',name:'标准品目标名称',start:'起始波数',end:'终止波数',points:'对齐点数',epochs:'训练轮数',samples_per_epoch:'每轮样本数',batch_size:'批大小',rf_samples:'RF样本数',trees:'树数量',device:'计算设备',preview_wavenumber:'成像波数',format:'导出格式',original:'包含原始数据',processed:'包含处理结果',instrument:'仪器布局',conversion:'转换方向' };
const CHOICES = { preprocessing_mode:[['auto','AirNet + PEER'],['prepared','使用当前输入']],engine:[['official','官方模型'],['agent','知识增强']],format:[['txt','TXT 数据'],['png','PNG 图像'],['bundle','完整结果包']],device:[['cpu','CPU'],['cuda','CUDA']],instrument:[['auto','自动识别'],['horiba','Horiba'],['nanophoton','Nanophoton']],conversion:[['horiba_to_nanophoton','Horiba → Nanophoton'],['nanophoton_to_horiba','Nanophoton → Horiba']] };
function Field({ label, value, rule, choices, onChange, disabled }) {
  usePreferences();
  if (rule?.boolean || typeof value === 'boolean') return <label className="qa-plan-check"><input type="checkbox" checked={!!value} disabled={disabled} onChange={e=>onChange(e.target.checked)} />{systemText(label)}</label>;
  const options=choices || rule?.options?.map(v=>[v,v]);
  return <label>{systemText(label)}{options ? <select disabled={disabled} value={value ?? ''} onChange={e=>onChange(e.target.value)}>{options.map(([v,name])=><option value={v} key={v}>{localize(name)}</option>)}</select>
    : <input disabled={disabled} type={typeof value==='number'||rule?.min!==undefined||value===null?'number':'text'} step={rule?.integer?1:'any'} min={rule?.min} max={rule?.max} value={value ?? ''} onChange={e=>onChange(e.target.value==='' && (rule?.nullable||value===null)?null:(typeof value==='number'||rule?.min!==undefined||value===null)?Number(e.target.value):e.target.value)} />}</label>;
}

export default function QAPlanCard({ plan, onPlan, base, headers, getContext, onRevise }) {
  usePreferences();
  const navigate=useNavigate();
  const [steps,setSteps]=useState(plan.steps),[catalog,setCatalog]=useState(null),[dirty,setDirty]=useState(false);
  const [working,setWorking]=useState(false),[error,setError]=useState(''),[units,setUnits]=useState(false),[sharing,setSharing]=useState(false);
  const [detailsOpen,setDetailsOpen]=useState(false);
  useEffect(()=>{setSteps(plan.steps);setDirty(false);setUnits(false);setSharing(false);},[plan.id,plan.revision]);
  useEffect(()=>{const abort=new AbortController();axios.get(`${base}/qa-assistant/actions/catalog`,{headers,signal:abort.signal}).then(r=>setCatalog(r.data)).catch(()=>{});return()=>abort.abort();},[plan.id]);
  const active=ACTIVE.includes(plan.status),draft=plan.status==='draft';
  function patch(index,key,value){setDirty(true);setSteps(old=>old.map((s,i)=>i===index?{...s,params:{...s.params,[key]:value}}:s));}
  function pipeline(index,sub,value){const next=[...steps[index].params.steps];next[sub]=value;patch(index,'steps',next);}
  async function act(fn){setWorking(true);setError('');try{await fn();}catch(e){setError(typeof e.response?.data?.detail==='string'?e.response.data.detail:e.message||localize("操作失败"));}finally{setWorking(false);}}
  async function run(){await act(async()=>{
    await checkPlanContext(getContext(), plan);
    let current=plan;
    if(dirty)current=(await axios.put(`${base}/qa-assistant/plans/${plan.id}`,{revision:plan.revision,steps:steps.map(({action,params})=>({action,params}))},{headers})).data;
    onPlan(current);
    onPlan(await executeQAPlan(base, current, headers, { units, sharing }));
    setDetailsOpen(false);
  });}
  async function download(entry){await act(async()=>{const {data}=await axios.get(`${base}/qa-assistant/plans/${plan.id}/artifacts/${entry.download_index}`,{headers,responseType:'blob'});const url=URL.createObjectURL(data);const a=document.createElement('a');a.href=url;a.download=entry.filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});}
  const directSteps = plan.direct_preprocess && steps.length === 1 && steps[0].action === 'preprocess' ? steps[0].params.steps : null;
  const title = directSteps ? directSteps.filter(step => step.enabled !== false).map(step => localize(STEP_TYPES[step.type])).join(' → ') || localize('智能光谱处理') : plan.title;
  const processingStatus = plan.progress?.steps?.[0]?.result_summary?.processing_steps || [];
  const parameterTitle = localize(draft ? '查看/修改算法与参数' : '查看算法与参数');
  const parameterFields = steps.map((step, i) => (
    <div className="qa-plan-fields" key={i}>
      {!directSteps && <strong>{systemText(step.label || step.action)}</strong>}
      {Object.entries(step.params).map(([key, value]) => {
        if (key !== 'steps') {
          return <Field key={key} label={systemText(FIELD[key] || key)} value={value}
            rule={catalog?.parameter_rules?.[step.action]?.[key]} choices={CHOICES[key]}
            disabled={!draft || working} onChange={next => patch(i, key, next)} />;
        }
        const registry = step.action === 'hyperspectral' ? catalog?.hyperspectral_registry : catalog?.pipeline_registry;
        return <div className="qa-plan-pipeline" key={key}>{value.map((s, n) => {
          const methods = (registry || []).filter(item => item.type === s.type);
          const spec = methods.find(item => item.method === s.method);
          return <div className="qa-plan-algorithm" key={s.id || n}>
            <label className="qa-plan-check">
              <input type="checkbox" checked={s.enabled !== false} disabled={!draft || working}
                onChange={e => pipeline(i, n, { ...s, enabled: e.target.checked })} />
              {localize('启用步骤 ')}{n + 1}
            </label>
            <label>{localize('算法')}
              <select aria-label={`${localize('步骤')}${i + 1}-${n + 1}${localize('算法')}`}
                disabled={!draft || working || !methods.length} value={s.method} onChange={e => {
                  const next = methods.find(item => item.method === e.target.value);
                  pipeline(i, n, { ...s, method: next.method, label: next.label,
                    params: Object.fromEntries(Object.entries(next.params).map(([name, rule]) => [name, rule.default])) });
                }}>
                {!spec && <option value={s.method} disabled>{systemText(s.label || s.method)}</option>}
                {methods.map(item => <option key={item.method} value={item.method}>{systemText(item.label)}</option>)}
              </select>
            </label>
            {Object.entries(s.params).map(([name, value]) => (
              <Field key={name} label={spec?.params[name]?.label || name} value={value} rule={spec?.params[name]}
                disabled={!draft || working} onChange={next => pipeline(i, n, { ...s, params: { ...s.params, [name]: next } })} />
            ))}
          </div>;
        })}</div>;
      })}
    </div>
  ));
  return <section className="qa-plan-card" data-plan-id={plan.id} aria-label={localize("可运行方案")}><div className="qa-plan-heading"><strong>{title}</strong><span>{systemText(STATUS[plan.status]||plan.status)}</span></div>
    {(!directSteps || draft) && <p className="qa-plan-summary">{directSteps ? localize('检查步骤和参数后运行。') : plan.summary}</p>}<small>{localize("数据：")}{plan.source_name}{plan.file_count>1?` · ${plan.file_count}${localize("项")}`:''}</small>
    {plan.input_summary?.points&&<small>{plan.input_summary.points}{localize(" 个点 · ")}{plan.input_summary.wavenumber_min}–{plan.input_summary.wavenumber_max} cm⁻¹{plan.input_summary.shape?`${localize(" · 尺寸 ")}${plan.input_summary.shape.join(' × ')}`:''}</small>}
    {(plan.input_summary?.warnings||[]).map((warning,i)=><small className="qa-warning" key={i}>{systemText(warning)}</small>)}
    <ol className="qa-plan-stages">{directSteps ? directSteps.map(step => {
      const status = processingStatus.find(record => record.id === step.id)?.status;
      const resultLabel = step.enabled === false || status === 'skipped' ? localize('已跳过') : status === 'done' ? localize('已完成') : status === 'failed' ? localize('失败') : '';
      const method = systemText(catalog?.pipeline_registry?.find(item => item.type === step.type && item.method === step.method)?.label || step.label || step.method);
      return <li key={step.id}><span>{localize(STEP_TYPES[step.type])}</span><small className="qa-plan-methods">{method}{resultLabel ? ` · ${resultLabel}` : ''}</small></li>;
    }) : steps.map((step,i)=>{const progress=plan.progress?.steps?.find(s=>s.index===i);return <li key={i}><span>{systemText(step.label||catalog?.operations.find(o=>o.action===step.action)?.label||step.action)}</span>{step.params.steps?.length>0&&<small className="qa-plan-methods">{systemText(step.params.steps.filter(s=>s.enabled!==false).map(s=>systemText((step.action==='hyperspectral'?catalog?.hyperspectral_registry:catalog?.pipeline_registry)?.find(r=>r.type===s.type&&r.method===s.method)?.label||s.method)).join(' → '))}</small>}{progress && <small>{systemText(STATUS[progress.status]||progress.status)}{progress.progress?.percent!==undefined?` · ${Math.floor(progress.progress.percent)}%`:''}</small>}</li>;})}</ol>
    {directSteps && <section className="qa-plan-parameters" aria-label={parameterTitle}>
      <h4>{parameterTitle}</h4>
      {parameterFields}
    </section>}
    {draft&&plan.needs_units&&<label className="qa-plan-check"><input type="checkbox" checked={units} onChange={e=>setUnits(e.target.checked)} />{localize("确认所选光谱横轴为拉曼位移 cm⁻¹，并同意所示格式转换")}</label>}
    {draft&&plan.needs_sharing&&<label className="qa-plan-check"><input type="checkbox" checked={sharing} onChange={e=>setSharing(e.target.checked)} />{localize("向当前项目成员共享所选数据、参数和结果")}</label>}
    {(error||plan.error)&&<p className="qa-error" role="alert">{systemText(error||plan.error)}</p>}
    {draft&&<><small>{localize("保留原始数据，结果另存。")}{dirty?localize("参数已修改，将校验后运行。"):''}</small><button className="qa-plan-run" disabled={working||(plan.needs_units&&!units)||(plan.needs_sharing&&!sharing)} onClick={run}>{working?localize("正在提交…"):localize("一键运行")}</button>{!directSteps && <button className="qa-plan-revise" disabled={working} onClick={()=>onRevise(`${localize("请修改刚才的方案：")}${plan.title}。`)}>{localize("继续对话修改方案")}</button>}</>}
    {!directSteps && <details open={detailsOpen} onToggle={e=>setDetailsOpen(e.currentTarget.open)}>
      <summary>{draft ? localize('查看 / 修改参数') : localize('查看执行参数')}</summary>
      {parameterFields}
    </details>}
    {steps.some(s=>s.action==='ssnet_train')&&<small>{localize("训练会占用本机计算资源，实际耗时取决于样本和参数。")}</small>}
    {active&&<button disabled={working||plan.status==='stopping'} onClick={()=>act(async()=>onPlan((await axios.post(`${base}/qa-assistant/plans/${plan.id}/cancel`,{},{headers})).data))}>{plan.status==='stopping'?localize("将在安全边界停止"):localize("停止方案")}</button>}
    {active&&<small>{localize("可继续提问。停止会取消后续步骤；不支持中断的当前算法完成后停止。")}</small>}
    {(plan.progress?.steps||[]).filter(s=>s.status==='completed'||s.url).map((entry,i)=><div className="qa-plan-result" key={i}><small>{systemText(entry.label)} · {systemText(STATUS[entry.status]||entry.status)}</small>{entry.url&&<button onClick={()=>navigate(entry.url)}>{localize("查看")}{entry.status==='completed'?localize("结果"):localize("任务")}</button>}{entry.download_index!==undefined&&<button disabled={working} onClick={()=>download(entry)}>{localize("下载文件")}</button>}</div>)}
    {!directSteps&&!active&&!draft&&<button onClick={()=>onRevise(`${localize("基于“")}${plan.title}${localize("”继续调整：")}`)}>{localize("继续讨论调整")}</button>}
  </section>;
}
