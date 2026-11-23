import React from 'react';
import Plot from './SizedPlot';
import {usePreferences} from '../i18n';
import '../pages/PeakFittingPage.css';

const COLORS=['#3b82f6','#d99a36','#8b73d7','#36a69c','#e5768b','#8ca83f','#bd7a50','#38a7c7','#a67bc5','#d4ad43','#6696a5','#c76b8f'];
export const fitNumber = (value, precision=7) => value == null || !Number.isFinite(value) ? '—' : Number(value.toPrecision(precision)).toString();

export function PeakFitChart({result, dark, txt, onPick, compact=false}) {
  const color=dark?'#b7c4d5':'#637389',grid=dark?'rgba(160,180,210,.12)':'rgba(80,100,130,.1)';
  const x=result.wavenumber;
  const hasFit = Boolean(result.intensity?.length);
  const observedColor = dark ? '#becee1' : '#71869d';
  const markerInterval = Math.max(1, Math.ceil(x.length / 60));
  const data = [];
  if (hasFit) data.push({x,y:result.intensity,name:txt('总拟合','Total fit'),type:'scatter',mode:'lines',legendrank:1,line:{color:dark?'#65d4d1':'#087e8b',width:2}});
  data.push({x,y:result.observed,name:txt('输入光谱','Input spectrum'),type:'scatter',mode:hasFit?'lines+markers':'lines',legendrank:0,
    line:{color:observedColor,width:hasFit?1:1.5,...(hasFit?{dash:'dot'}:{})},
    ...(hasFit?{marker:{color:observedColor,size:x.map((_,index)=>index%markerInterval===0?4:0)}}:{})});
  result.components?.forEach((y,i)=>data.push({x,y,name:`${txt('分峰','Peak')} ${i+1}`,type:'scatter',mode:'lines',line:{color:COLORS[i%COLORS.length],width:1.4,dash:'dash'}}));
  const hasResidual=!!result.residual?.length;
  if(hasResidual)data.push({x,y:result.residual,name:txt('残差','Residual'),type:'scatter',mode:'lines',yaxis:'y2',line:{color:dark?'#c8a4ef':'#8b73d7',width:1},showlegend:false});
  return <div className="pf-chart"><Plot data={data} onClick={onPick} layout={{height:compact?250:490,paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',
    font:{color,size:11},margin:{l:64,r:18,t:compact?15:58,b:50},hovermode:'x unified',dragmode:'zoom',uirevision:`${x[0]}:${x.at(-1)}:${x.length}:${hasResidual}`,
    legend:{orientation:'h',x:0,y:1.15},xaxis:{title:{text:txt('拉曼位移 (cm⁻¹)','Raman shift (cm⁻¹)')},gridcolor:grid,zeroline:false,anchor:hasResidual?'y2':'y'},
    yaxis:{title:{text:txt('强度','Intensity')},gridcolor:grid,zeroline:false,domain:hasResidual?[.32,1]:[0,1]},
    ...(hasResidual?{yaxis2:{title:{text:txt('残差','Residual')},domain:[0,.2],gridcolor:grid,zeroline:true,zerolinecolor:grid}}:{})}}
    config={{responsive:true,displaylogo:false,scrollZoom:false,toImageButtonOptions:{filename:'peak_fit',scale:2}}} style={{width:'100%',height:compact?250:490}} useResizeHandler /></div>;
}

export default function PeakFitResult({result,dark}) {
  const {language}=usePreferences(),txt=(zh,en)=>language==='zh'?zh:en;
  if(!result?.peaks)return null;
  const messages={
    uncertainty:txt('部分参数的不确定度无法可靠估计，请检查初值、约束及数据点数。','Some parameter uncertainties cannot be estimated reliably. Review initial values, bounds and point count.'),
    correlated:txt('部分拟合参数高度相关。请结合参考谱，比较不同峰数和初值的稳定性。','Some fit parameters are highly correlated. Use reference spectra and compare stability across peak counts and initial values.'),
    bound:txt('参数接近约束边界，请检查该峰的初值和范围。','A parameter is close to a bound. Review this peak’s initial values and limits.')};
  return <div className="pf-result">
    <div className="pf-metrics"><div><small>R²</small><strong>{fitNumber(result.r_squared)}</strong></div><div><small>RMSE</small><strong>{fitNumber(result.rmse,4)}</strong></div><div><small>{txt('分峰数 / 数据点','Peaks / points')}</small><strong>{result.peaks.length} / {result.points}</strong></div></div>
    <PeakFitChart result={result} dark={dark} txt={txt}/>
    <p className="sg-help">{txt('圆点标记拟合区间内的输入数据，实线是各分峰相加得到的总拟合。点击图例可单独查看曲线。','Dots mark the input data in the fitting range. The solid line is the sum of the fitted peaks. Click a legend item to toggle its curve.')}</p>
    {(result.warnings||[]).map((w,i)=><p className="pf-warning" key={i}>{w.peak?`${txt('分峰','Peak')} ${w.peak} · `:''}{messages[w.code]||w.code}</p>)}
    <div className="pf-table-wrap"><table className="pf-table"><thead><tr>{[txt('分峰','Peak'),txt('峰位','Center'),txt('峰面积','Area'),txt('峰高','Height'),txt('宽度参数','Width parameter'),txt('实际 FWHM','Actual FWHM'),'η'].map(v=><th key={v}>{v}</th>)}</tr></thead><tbody>{result.peaks.map(p=><tr key={p.index}><td><span className="pf-peak-dot" style={{background:COLORS[(p.index-1)%COLORS.length]}}/>{p.index}</td>{[p.center,p.area,p.height,p.width_parameter,p.fwhm,p.eta].map((v,i)=><td key={i}>{fitNumber(v)}</td>)}</tr>)}</tbody></table></div>
    <p className="sg-help">{txt('峰位、宽度及 FWHM 的单位为 cm⁻¹；峰面积是完整峰形的积分面积。宽度参数沿用原算法的高斯／洛伦兹宽度分配，实际 FWHM 由最终峰形计算。','Centers, widths and FWHM are in cm⁻¹. Area is the full analytic peak area. The width parameter controls the Gaussian/Lorentzian widths; actual FWHM is measured from the fitted profile.')}</p>
    <p className="sg-help">{txt('峰数与峰归属需要结合参考谱或文献判断；较高的 R² 不代表分峰方案唯一或物质身份已确认。','Peak count and assignments require reference spectra or literature. A high R² does not establish a unique decomposition or chemical identity.')}</p>
  </div>;
}
