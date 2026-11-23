import { systemText, localize } from '../locale.js';
import { usePreferences } from '../i18n';
import React, {useEffect,useState} from 'react';
import Plot from './SizedPlot';
import SpectralChart from './SpectralChart';
import {apiErrorMessage} from '../auth';
import {HYPERSPECTRAL_COLORSCALE,heatmapLimits} from './hyperComparison';

function savedPreview(run, error) {
  const {result,input}=run;
  if (!error || !result.preview?.length) return null;
  const mode=result.summary?.mode || input.mode;
  return {mode,preview:result.preview,preview_x:result.preview_x || result.wavenumber,preview_y:result.preview_y,
    preview_wavenumber:mode==='time_series'?null:result.preview_wavenumber,saved:true};
}

export default function HyperspectralHistoryResult({run,api,dark,onModeChange,onWavenumberChange,onPixelChange,initialWavenumber}) {
  usePreferences();
  const axis=run.result.wavenumber || run.input.wavenumber || [];
  const requested=initialWavenumber!==null && initialWavenumber!==undefined && initialWavenumber!==''?Number(initialWavenumber):NaN;
  const [mode,setMode]=useState('compare'), [wave,setWave]=useState(Number.isFinite(requested)?requested:run.result.preview_wavenumber ?? axis[Math.floor(axis.length/2)] ?? '');
  const [views,setViews]=useState({}), [errors,setErrors]=useState({}), [loading,setLoading]=useState(false), [point,setPoint]=useState(null), [pixels,setPixels]=useState({});
  const ends=values=>values?.length?[Math.min(values[0],values.at(-1)),Math.max(values[0],values.at(-1))]:null;
  const ranges=[ends(run.input.wavenumber),ends(run.result.wavenumber)].filter(Boolean);
  const minimum=Math.max(...ranges.map(range=>range[0])),maximum=Math.min(...ranges.map(range=>range[1]));
  useEffect(()=>{onPixelChange?.(point);},[point]);
  useEffect(()=>{onWavenumberChange?.(wave);},[wave]);
  useEffect(()=>{
    let cancelled=false;setLoading(true);setViews({});setErrors({});
    Promise.allSettled(['original','processed'].map(role=>api.get(`/analysis-runs/${run.id}/visualization`,{params:{role,wavenumber:wave===''?undefined:wave}}))).then(results=>{
      if(cancelled)return;
      const next={},issues={};results.forEach((result,index)=>{const role=['original','processed'][index];if(result.status==='fulfilled')next[role]=result.value.data;else issues[role]=apiErrorMessage(result.reason);});
      setViews(next);setErrors(issues);setLoading(false);
    });
    return()=>{cancelled=true;};
  },[api,run.id,wave]);
  useEffect(()=>{
    if(!point)return;
    let cancelled=false;setPixels({});
    Promise.allSettled(['original','processed'].map(role=>api.get(`/analysis-runs/${run.id}/visualization`,{params:{role,x:point.x,y:point.y,wavenumber:wave===''?undefined:wave}}))).then(results=>{
      if(cancelled)return;
      const next={};results.forEach((result,index)=>{if(result.status==='fulfilled')next[['original','processed'][index]]=result.value.data.pixel;});setPixels(next);
    });return()=>{cancelled=true;};
  },[api,run.id,wave,point]);
  const roles=mode==='compare'?['original','processed']:[mode];
  const raw=views.original?.mean_spectrum || (run.input.mean_spectrum?{wavenumber:run.input.wavenumber,intensity:run.input.mean_spectrum}:null);
  const processed=views.processed?.mean_spectrum || (run.result.mean_spectrum?{wavenumber:run.result.wavenumber,intensity:run.result.mean_spectrum}:null);
  const processedView=views.processed || savedPreview(run, errors.processed);
  const seriesMode=(views.original?.mode || processedView?.mode || run.input.mode)==='time_series';
  const limits=heatmapLimits(views.original?.preview,processedView?.preview);
  const layout={autosize:true,height:325,margin:{l:55,r:35,t:15,b:55},paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{color:dark?'#cbd5e1':'#64748b'}};
  return <section className="history-hyperspectral-result">
    <div className="dw-heading"><h3>{localize("平均光谱与成像")}</h3><nav className="dw-actions" aria-label={localize("高光谱结果视图")}>{[['compare',localize("对比")],['original',localize("原始")],['processed',localize("处理后")]].map(([key,label])=><button key={key} aria-pressed={mode===key} onClick={()=>{setMode(key);onModeChange?.(key);}}>{systemText(label)}</button>)}</nav></div>
    <SpectralChart rawData={mode==='processed'?null:raw} processedData={mode==='original'?null:processed} baselineData={mode==='original'||!processed?null:run.result.baseline_mean} rawLabel={localize("原始平均光谱")} processedLabel={localize("处理后平均光谱")} height={310} dark={dark} horizontalLegend/>
    {!seriesMode && <label className="dw-hyper-wave">{localize("成像波数 ")}<input aria-label={localize("成像波数")} type="number" min={Number.isFinite(minimum)?minimum:undefined} max={Number.isFinite(maximum)?maximum:undefined} key={`${run.id}:${wave}`} defaultValue={wave} onBlur={event=>{let value=Number(event.target.value);if(event.target.value && Number.isFinite(value)){if(ranges.length && minimum<=maximum)value=Math.max(minimum,Math.min(maximum,value));event.target.value=String(value);setWave(value);onWavenumberChange?.(value);}}}/> cm⁻¹</label>}
    {loading && <p role="status">{localize("正在读取成像数据…")}</p>}
    <div className={`dw-hyper-images ${mode==='compare'?'is-comparison':''}`}>{roles.map(role=>{
      const view=role==='original'?views.original:processedView, title=role==='original'?localize("原始"):localize("处理后"), series=view?.mode==='time_series';
      return <section key={role} data-hyper-role={role}><h3>{systemText(title)}{view?.preview_wavenumber!=null?` · ${view.preview_wavenumber.toFixed(1)} cm⁻¹`:''}</h3>
        {errors[role] && <p className="dw-error" role="status">{errors[role]}</p>}
        {view?.saved && <p className="dw-muted">{localize('显示该记录保存的成像预览。')}</p>}
        {view && <Plot data={[{type:'heatmap',name:title,z:view.preview,x:series?view.preview_x:undefined,y:series?view.preview_y:undefined,colorscale:HYPERSPECTRAL_COLORSCALE,...limits,colorbar:{title:localize("强度"),thickness:10},hovertemplate:series?'%{x} cm⁻¹ · %{y}<br>%{z}<extra></extra>':'X=%{x}, Y=%{y}<br>%{z}<extra></extra>'}]} layout={{...layout,xaxis:{title:series?localize("拉曼位移 (cm⁻¹)"):'X',constrain:'domain'},yaxis:{title:series?localize("采集序号"):'Y',autorange:'reversed',...(series?{}:{scaleanchor:'x',scaleratio:1,constrain:'domain'})}}} config={{responsive:true,displaylogo:false}} style={{width:'100%'}} useResizeHandler onClick={event=>{if(!view.saved && !series && event.points?.length){const pixel=event.points[0];setPoint({x:Math.round(pixel.x*(view.preview_scale || 1)),y:Math.round(pixel.y*(view.preview_scale || 1))});}}}/>}
      </section>;
    })}</div>
    {point && <section className="dw-pixel-result"><h3>{localize("像素光谱 · X=")}{point.x}，Y={point.y}</h3><SpectralChart rawData={mode==='processed'?null:pixels.original} processedData={mode==='original'?null:pixels.processed} rawLabel={localize("原始像素谱")} processedLabel={localize("处理后像素谱")} height={280} dark={dark} horizontalLegend/></section>}
  </section>;
}
