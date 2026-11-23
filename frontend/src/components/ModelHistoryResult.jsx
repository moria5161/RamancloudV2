import { systemValue, systemText, localize } from '../locale.js';
import { usePreferences } from '../i18n';
import React from 'react';
import LibraryMatchResults from './LibraryMatchResults';
import StructureGenerationResults from './StructureGenerationResults';
import MixtureResult from './MixtureResult';
import PeakFitResult from './PeakFitResult';
import SpectralChart from './SpectralChart';
import AnalysisRecordSteps, { RecordParameters, recordMethodLabel } from './AnalysisRecordSteps';
import '../pages/StructureGenerationPage.css';
import '../pages/LibraryMatchingPage.css';
import '../pages/MixtureAnalysisPage.css';

export const MODEL_ANALYSIS_TYPES=['library_matching','structure_generation','mixture_analysis','peak_fitting'];
export function historyTabs(type) {
  if(type==='peak_fitting') return [['overview',localize('拟合结果')],['process',localize('拟合设置')],['files',localize('数据与文件')]];
  if(type==='library_matching') return [['overview',localize("候选与谱图")],['process',localize("匹配设置")],['files',localize("数据与文件")]];
  if(type==='structure_generation') return [['overview',localize("候选结构")],['process',localize("生成设置")],['files',localize("数据与文件")]];
  if(type==='mixture_analysis') return [['overview',localize("解析结果")],['process',localize("解析信息")],['files',localize("数据与文件")]];
  return [['overview',localize("结果总览")],['process',localize("处理过程")],['files',localize("数据与文件")]];
}

function savedSpectrum(value) {
  return Array.isArray(value?.wavenumber) && value.wavenumber.length > 0 &&
    Array.isArray(value.intensity) && value.intensity.length === value.wavenumber.length ? value : null;
}

export default function ModelHistoryResult({run,api,dark,onError}) {
  const { language } = usePreferences();
  const type=run.analysis_type;
  const settings=run.steps?.find(step=>step.type===type)?.params || {};
  const job={id:run.result.job_id,status:'completed',source_name:run.source_name,created_at:run.created_at,
    profile:run.result.profile || {},settings,input:run.input,result:run.result};
  const txt = (zh, en) => language === 'zh' ? zh : en;
  const original=savedSpectrum(run.input.source?.spectrum) || savedSpectrum(run.input);
  const hasModelInput=type==='library_matching' || type==='structure_generation';
  const modelInput=savedSpectrum(run.result.model_input) || savedSpectrum(run.input.model_input);
  const spectra=<div className="dw-record-spectra">
    <section>
      <h3>{txt('原始输入光谱','Original input spectrum')}</h3>
      {original ? <SpectralChart rawData={original} height={255} dark={dark} showToolbar={false}/>
        : <p className="dw-muted">{txt('这条记录未保留完整输入光谱。','The full input spectrum was not saved with this record.')}</p>}
    </section>
    {hasModelInput && <section>
      <h3>{txt('模型输入光谱','Model input spectrum')}</h3>
      {modelInput ? <SpectralChart processedData={modelInput} height={255} dark={dark} showToolbar={false}/>
        : <p className="dw-muted">{txt('这条记录未保留模型输入光谱。','The model input spectrum was not saved with this record.')}</p>}
    </section>}
  </div>;
  return <div className="history-model-result" key={run.id}>
    {hasModelInput && spectra}
    {type==='peak_fitting' && <PeakFitResult result={run.result} dark={dark}/>}
    {type==='mixture_analysis' && <MixtureResult result={run.result} dark={dark}/>}
    {type==='library_matching' && <LibraryMatchResults job={job} api={api} dark={dark} txt={txt} onError={onError} history/>}
    {type==='structure_generation' && <StructureGenerationResults job={job} api={api} txt={txt} onError={onError} history/>}
    {!hasModelInput && spectra}
  </div>;
}
export function ModelHistorySettings({run}) {
  const {language}=usePreferences();
  const txt=(zh,en)=>language==='zh'?zh:en;
  const {analysis_type:type,input,result}=run;
  const step=run.steps?.find(item=>item.type===type);
  const settings=step?.params || {};
  const heading=historyTabs(type)[1][1];
  if(type==='peak_fitting') {
    const {peaks=[],...fitSettings}=settings;
    const bounds=(value, lower, upper)=>`${value ?? '—'} [${lower ?? '—'}, ${upper ?? '—'}]`;
    return <section>
      <h3>{heading} · {recordMethodLabel(step?.method || 'voigt')}</h3>
      <RecordParameters values={{...fitSettings,...(result.implementation ? {implementation:result.implementation} : {})}}/>
      {peaks.length>0 && <div className="pf-table-wrap"><table className="pf-table">
        <thead><tr>{[txt('分峰','Peak'),txt('峰形','Profile'),txt('峰位初值与范围','Initial center & bounds'),
          txt('宽度初值与范围','Initial width & bounds'),txt('面积初值与范围','Initial area & bounds'),'η'].map(t=><th key={t}>{t}</th>)}</tr></thead>
        <tbody>{peaks.map((p,i)=><tr key={i}><td>{i+1}</td><td>{p.shape}</td>
          <td>{bounds(p.center,p.center_min,p.center_max)}</td><td>{bounds(p.width,p.width_min,p.width_max)}</td>
          <td>{bounds(p.area ?? txt('自动','Auto'),p.area_min,p.area_max ?? '∞')}</td>
          <td>{p.shape==='gaussian'?0:p.shape==='lorentzian'?1:bounds(p.eta,p.eta_min,p.eta_max)}</td>
        </tr>)}</tbody>
      </table></div>}
    </section>;
  }
  if(type==='mixture_analysis') {
    const wave=result.wavenumber || [];
    const grid=result.processing?.grid || (wave.length ? {start:Math.min(wave[0],wave.at(-1)),end:Math.max(wave[0],wave.at(-1)),points:wave.length} : {});
    return <section>
      <h3>{heading} · SSnet (U-Net ECA + Random Forest)</h3>
      {result.model_name && <p>{localize('目标标准品模型')} · {result.model_name}</p>}
      <RecordParameters values={{...grid,
        ...(result.removed_offset != null ? {removed_offset:result.removed_offset} : {}),
        ...(result.processing?.normalization_scale != null ? {normalization_scale:result.processing.normalization_scale} : {})}}/>
      <h3>{txt('所用标准品模型的训练参数','Training settings for the selected standard model')}</h3>
      <RecordParameters values={result.processing?.training_parameters}/>
      {run.steps?.length > 0 && <>
        <h3>{localize('输入预处理记录')}</h3>
        <AnalysisRecordSteps steps={run.steps}/>
      </>}
    </section>;
  }
  const autoLibrary=type==='library_matching' && (result.preprocessing_mode || settings.preprocessing_mode)==='auto';
  return <section>
    <h3>{heading} · {recordMethodLabel(step?.method || (type==='library_matching'?'peaknet':'vib2mol'))}</h3>
    {result.profile?.label && <p>{systemText(result.profile.label)}</p>}
    <RecordParameters values={settings}/>
    {autoLibrary && <section className="dw-step">
      <h4>{txt('输入预处理','Input preprocessing')} · PEER → AirNet</h4>
      <RecordParameters values={Object.fromEntries([
        ['peer_window',result.profile?.peer_window],['peer_iterations',result.profile?.peer_iterations],
        ['baseline_lambda',result.profile?.baseline_lambda],['baseline_iterations',result.profile?.baseline_iterations],
        ['iterations',result.preprocessing?.iterations],
      ].filter(([,value])=>value!=null))}/>
    </section>}
    <details className="dw-step">
      <summary>{localize('输入与模型记录')}</summary>
      <pre className="dw-parameter-value">{JSON.stringify(systemValue({
        source:input.source?.reference,profile:result.profile,preparation:input.model_input?.preparation || input.cropped?.preparation,
        normalization_scale:result.normalization_scale,
      }),null,2)}</pre>
    </details>
  </section>;
}
