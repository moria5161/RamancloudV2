import { usePreferences } from '../i18n';
import { systemText } from '../locale.js';
import React, {useState} from 'react';
import Plot from 'react-plotly.js';

export default function MixtureResult({result, dark, txt: providedTxt}) {
  const { language } = usePreferences();
  const txt = providedTxt || ((zh, en) => language === 'zh' ? zh : en);
  const [shown,setShown]=useState({mixture:true,extracted:true,background:true});
  const roles=[['mixture',txt('混合谱（减最小值后）','Mixture (min shifted)'),'#94a3b8'],['extracted',txt('目标提取谱','Extracted target'),'#087e8b'],['background',txt('估计背景','Estimated background'),'#bb8b5a']];
  return <section className="history-mixture-result">
    <div className="mx-output-facts"><span>{txt('目标物质','Target')}<strong>{result.model_name || '—'}</strong></span><span>{txt('RF 识别得分','RF score')}<strong>{Number.isFinite(result.rf_score)?result.rf_score.toFixed(3):'—'}</strong></span><span>{txt('耗时','Duration')}<strong>{result.duration_seconds ?? '—'} s</strong></span></div>
    <div className="dw-actions" role="group" aria-label={txt('解析曲线','Extraction curves')}>{roles.filter(([role])=>Array.isArray(result[role])).map(([role,label])=><button key={role} aria-pressed={shown[role]} onClick={()=>setShown(previous=>({...previous,[role]:!previous[role]}))}>{systemText(label)}</button>)}</div>
    <Plot data={roles.filter(([role])=>shown[role] && Array.isArray(result[role])).map(([role,name,color])=>({x:result.wavenumber,y:result[role],name,type:'scatter',mode:'lines',line:{color,width:role==='extracted'?2:1.3}}))} layout={{autosize:true,height:365,margin:{l:60,r:20,t:20,b:85},paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{color:dark?'#cbd5e1':'#64748b',size:12},xaxis:{title:'Raman shift (cm⁻¹)'},yaxis:{title:txt('强度','Intensity')},legend:{orientation:'h',y:-.25},hovermode:'x unified',uirevision:'mixture-result'}} config={{responsive:true,displaylogo:false,scrollZoom:false}} style={{width:'100%'}} useResizeHandler/>
    <p className="dw-muted">{txt('目标信号 = 混合谱 − 估计背景；RF 得分不代表浓度或检出限。','Target = mixture − estimated background; RF is not concentration or detection limit.')}</p>
  </section>;
}
