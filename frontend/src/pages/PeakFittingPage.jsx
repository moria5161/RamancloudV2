import React,{useEffect,useMemo,useRef,useState} from 'react';
import axios from 'axios';
import {useSearchParams} from 'react-router-dom';
import {LineChart as ChartNoAxesCombined,Upload,Plus,Trash2,MousePointer2,Loader2,ArrowRight} from 'lucide-react';
import {useAuth,apiErrorMessage} from '../auth';
import {usePreferences} from '../i18n';
import {systemText} from '../locale.js';
import {NewAnalysisButton,useWorkspaceList} from '../components/AnalysisWorkspaces';
import {SPECTRAL_ACCEPT} from '../components/ImportReport';
import ImportReport from '../components/ImportReport';
import SpectrumImportConfirmation from '../components/SpectrumImportConfirmation';
import ModuleUploadHistory from '../components/ModuleUploadHistory';
import ModuleInputActions from '../components/ModuleInputActions';
import SavedAnalysisRecords from '../components/SavedAnalysisRecords';
import {moduleSpectrum} from '../components/moduleSpectrum';
import {workflowSpectrum} from './structureGeneration';
import {hasBaseline} from './libraryMatching';
import PeakFitResult,{PeakFitChart} from '../components/PeakFitResult';
import {FileExport} from '../components/ResultActions';
import './StructureGenerationPage.css';
import './PeakFittingPage.css';

const BASE=`${import.meta.env.BASE_URL.replace(/\/$/,'')}/api`;
export function initialPeak(center,width,start,end){return {center,center_min:Math.max(start,center-1),center_max:Math.min(end,center+1),width,width_min:width*.9,width_max:width*1.1,area:null,area_min:0,area_max:null,eta:.5,eta_min:0,eta_max:1,shape:'voigt'};}
export default function PeakFittingPage(){
  const {token}=useAuth(),{language,theme}=usePreferences(),txt=(zh,en)=>language==='zh'?zh:en;
  const api=useMemo(()=>axios.create({baseURL:BASE,headers:{Authorization:`Bearer ${token}`}}),[token]);
  const [search,setSearch]=useSearchParams(),requestedJob=search.get('job'),requestedTask=search.get('task'),requestedVersion=search.get('version');
  const [source,setSource]=useState(null),[tasks,setTasks]=useState([]),[task,setTask]=useState(null),[version,setVersion]=useState('');
  const [tab,setTab]=useState('upload'),[start,setStart]=useState(''),[end,setEnd]=useState(''),[peaks,setPeaks]=useState([]),[job,setJob]=useState(null);
  const [baseline,setBaseline]=useState(false),[units,setUnits]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[pending,setPending]=useState(null),[dirty,setDirty]=useState(false),[picking,setPicking]=useState(false);
  const fileRef=useRef(),resultRef=useRef(),sequence=useRef(0),mounted=useRef(true);
  const active=['queued','running'].includes(job?.status),locked=busy||active||!!pending;
  useEffect(()=>{if(job?.status==='completed'){const frame=requestAnimationFrame(()=>{if(resultRef.current?.getClientRects().length)resultRef.current.scrollIntoView({block:'start',behavior:'smooth'});});return()=>cancelAnimationFrame(frame);}},[job?.id,job?.status]);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;sequence.current++;};},[]);
  useWorkspaceList(api,'/ai-workflows',setTasks,setError);
  function choose(input){
    sequence.current++;setSource(input);setJob(null);setDirty(false);setError('');setPicking(false);
    const x=input.spectrum.wavenumber,y=input.spectrum.intensity,lo=Math.min(x[0],x.at(-1)),hi=Math.max(x[0],x.at(-1));
    let max=0;for(let i=1;i<y.length;i++)if(y[i]>y[max])max=i;
    const center=Math.max(lo,Math.min(hi,x[max])),width=Math.max((hi-lo)/20,Math.abs(x[1]-x[0])*3);
    setStart(lo);setEnd(hi);setPeaks([initialPeak(center,width,lo,hi)]);setBaseline(hasBaseline(input.steps));setUnits(false);
  }
  function restore(value){
    const snapshot=value.input.source;setSource({name:value.source_name,...snapshot,reuse_job_id:value.id,kind:'saved'});
    setJob(value);setStart(value.settings.start);setEnd(value.settings.end);setPeaks(value.settings.peaks);setUnits(value.settings.unit_confirmed);setBaseline(true);setDirty(false);setPicking(false);setPending(null);setError('');
  }
  useEffect(()=>{
    if(!requestedJob)return;const abort=new AbortController();setBusy(true);
    api.get(`/peak-fitting/jobs/${encodeURIComponent(requestedJob)}`,{signal:abort.signal}).then(({data})=>{if(!abort.signal.aborted)restore(data);}).catch(e=>{if(!abort.signal.aborted)setError(apiErrorMessage(e));}).finally(()=>{if(!abort.signal.aborted)setBusy(false);});
    return()=>abort.abort();
  },[requestedJob,api]);
  async function loadWorkflow(id,vid){
    if(!id)return;setBusy(true);setError('');const revision=++sequence.current;
    try{
      const current=(await api.get(`/ai-workflows/${encodeURIComponent(id)}`)).data;
      const complete=current.versions.filter(v=>v.status==='completed');if(!complete.length)throw Error(txt('请先完成光谱处理，再选择已保存的版本。','Complete preprocessing and select a saved version first.'));
      const selected=vid||complete.at(-1).id,result=(await api.get(`/ai-workflows/${encodeURIComponent(id)}/versions/${encodeURIComponent(selected)}`)).data;
      if(!mounted.current||revision!==sequence.current)return;choose(workflowSpectrum(current,result));setTask(current);setVersion(selected);setTab('processed');
    }catch(e){if(mounted.current&&revision===sequence.current)setError(apiErrorMessage(e,e.message));}finally{if(mounted.current)setBusy(false);}
  }
  useEffect(()=>{if(requestedTask&&!requestedJob)loadWorkflow(requestedTask,requestedVersion);},[requestedTask,requestedVersion,requestedJob,api]);
  useEffect(()=>{
    if(!active)return;let timer,cancelled=false;
    async function poll(){try{const {data}=await api.get(`/peak-fitting/jobs/${job.id}`);if(cancelled)return;setJob(data);if(['queued','running'].includes(data.status))timer=setTimeout(poll,800);else setDirty(false);}catch(e){if(!cancelled){setError(apiErrorMessage(e));if(e.response?.status!==403&&e.response?.status!==404)timer=setTimeout(poll,2500);else setJob(null);}}}
    timer=setTimeout(poll,500);return()=>{cancelled=true;clearTimeout(timer);};
  },[active,job?.id,api]);
  async function upload(file,confirmed=false,spectrumIndex){
    if(!file)return;setBusy(true);setError('');const revision=++sequence.current;
    try{const form=new FormData();form.append('file',file);form.append('confirm_conversion',String(confirmed));if(spectrumIndex!=null)form.append('spectrum_index',String(spectrumIndex));
      const {data}=await api.post('/peak-fitting/sources/upload',form);if(!mounted.current||revision!==sequence.current)return;
      if(data.requires_confirmation){setPending({file,inspection:data});return;}setPending(null);choose(moduleSpectrum(data,'peak-fitting'));setTask(null);setVersion('');setSearch({}, {replace:true});
    }catch(e){if(mounted.current)setError(apiErrorMessage(e));}finally{if(mounted.current)setBusy(false);if(fileRef.current)fileRef.current.value='';}
  }
  async function example(){
    setBusy(true);setError('');try{const {data}=await api.get('/peak-fitting/example');const file=new File([data.spectrum.wavenumber.map((x,i)=>`${x}\t${data.spectrum.intensity[i]}`).join('\n')],'simulated_three_peaks.txt',{type:'text/plain'});
      const form=new FormData();form.append('file',file);const response=await api.post('/peak-fitting/sources/upload',form);if(!mounted.current)return;
      choose(moduleSpectrum(response.data,'peak-fitting'));setStart(data.settings.start);setEnd(data.settings.end);setPeaks(data.settings.peaks);setBaseline(true);setUnits(true);setTask(null);setVersion('');setSearch({}, {replace:true});
    }catch(e){if(mounted.current)setError(apiErrorMessage(e));}finally{if(mounted.current)setBusy(false);}
  }
  function edit(index,key,value){setPeaks(old=>old.map((p,i)=>{
    if(i!==index)return p;const next={...p,[key]:value};
    if(key==='center'&&Number.isFinite(value)&&Number.isFinite(p.center)){
      const delta=value-p.center;next.center_min=Math.max(Number(start),p.center_min+delta);next.center_max=Math.min(Number(end),p.center_max+delta);
    }
    if(key==='width'&&Number.isFinite(value)&&value>0&&p.width>0){next.width_min=p.width_min*value/p.width;next.width_max=p.width_max*value/p.width;}
    return next;
  }));setDirty(true);}
  function addPeak(center){if(!source||peaks.length>=12)return;const width=Math.max((Number(end)-Number(start))/25,Math.abs(source.spectrum.wavenumber[1]-source.spectrum.wavenumber[0])*2);setPeaks(old=>[...old,initialPeak(center??(Number(start)+Number(end))/2,width,Number(start),Number(end))]);setDirty(true);setPicking(false);}
  async function run(){
    setBusy(true);setError('');try{
      const ref=source.reference||{},origin=source.reuse_job_id?{reuse_job_id:source.reuse_job_id}:{source_id:ref.source_id,workflow_id:ref.workflow_id,version_id:ref.version_id};
      const payload={...origin,start:Number(start),end:Number(end),peaks,unit_confirmed:units,baseline_confirmed:baseline};
      await api.post('/peak-fitting/validate',payload);
      const {data}=await api.post('/peak-fitting/jobs',payload);if(!mounted.current)return;setJob(data);setDirty(false);setSearch({job:data.id},{replace:true});
    }catch(e){if(mounted.current)setError(apiErrorMessage(e));}finally{if(mounted.current)setBusy(false);}
  }
  async function download(kind){const {data}=await api.get(`/peak-fitting/jobs/${job.id}/download`,{params:{kind},responseType:'blob'});const url=URL.createObjectURL(data),a=document.createElement('a');a.href=url;a.download=`${(job.source_name||'spectrum').replace(/\.[^.]+$/,'')}_peak_fit.${{parameters:'csv',curves:'tsv',png:'png',bundle:'zip'}[kind]}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  const number=(index,key,label,options={})=><label>{label}<input aria-label={`${txt('分峰','Peak')} ${index+1} ${label}`} type="number" step="any" disabled={locked} value={peaks[index][key]??''} {...options} onChange={e=>edit(index,key,e.target.value===''?null:Number(e.target.value))}/></label>;
  const complete=job?.status==='completed';
  return <div className="sg-workspace pf-workspace" data-qa-run={job?.analysis_run_id||undefined} data-qa-state={JSON.stringify({module:'peak-fitting',status:job?.status||(source?'loaded':'empty'),peaks:peaks.length,range:[start,end],baseline_confirmed:baseline,unsaved_changes:dirty})}>
    <header className="sg-header"><div><h1><ChartNoAxesCombined size={27}/>{txt('分峰拟合','Peak fitting')}</h1><p>{txt('在已校正基线的光谱上，设置峰数、初值和约束，比较分峰、总拟合与残差。','Fit baseline-corrected spectra with editable peak counts, initial values and bounds. Compare components, total fit and residuals.')}</p></div><NewAnalysisButton txt={txt} disabled={locked}/></header>
    <div className="sg-flow">{[txt('准备光谱','Prepare spectrum'),txt('设置分峰','Set peaks'),txt('拟合与比较','Fit & compare'),txt('记录与导出','Record & export')].map((s,i)=><div key={s}><span>{i+1}</span>{s}</div>)}</div>
    {error&&<div className="sg-alert is-error" role="alert">{systemText(error)}</div>}{job?.status==='failed'&&<div className="sg-alert is-error" role="alert">{systemText(job.error)}</div>}
    <div className="pf-layout"><div className="sg-input-column">
      <section className="sg-panel"><div className="sg-panel-heading"><h2><span>01</span>{txt('输入光谱','Input spectrum')}</h2></div>
        <div className="sg-source-tabs">{[['upload',txt('本地上传','Upload')],['processed',txt('处理结果','Processed spectra')]].map(([key,label])=><button key={key} disabled={locked} aria-selected={tab===key} onClick={()=>setTab(key)}>{label}</button>)}</div>
        {tab==='upload'?<><input hidden ref={fileRef} type="file" accept={SPECTRAL_ACCEPT} aria-label={txt('上传拟合光谱','Upload fitting spectrum')} onChange={e=>upload(e.target.files[0])}/><button className="sg-upload" disabled={locked} onClick={()=>fileRef.current.click()}><Upload size={25}/><strong>{txt('上传已完成基线校正的光谱','Upload a baseline-corrected spectrum')}</strong><span>TXT · CSV · XLSX · JCAMP · WDF · WXD · L6M · NPG</span></button><ModuleUploadHistory api={api} module="peak-fitting" revision={source?.reference?.source_id} txt={txt} disabled={locked} onError={setError} onSelect={data=>{choose(moduleSpectrum(data,'peak-fitting'));setSearch({},{replace:true});}}/></>:<div className="sg-source-selectors"><label>{txt('光谱任务','Spectrum task')}<select aria-label={txt('光谱任务','Spectrum task')} disabled={locked} value={task?.id||''} onChange={e=>{setSearch({},{replace:true});loadWorkflow(e.target.value);}}><option value="">{txt('选择已处理的光谱','Select a processed spectrum')}</option>{tasks.map(t=><option key={t.id} value={t.id}>{t.source_name}</option>)}</select></label>{task&&<label>{txt('已完成版本','Completed version')}<select aria-label={txt('已完成版本','Completed version')} disabled={locked} value={version} onChange={e=>loadWorkflow(task.id,e.target.value)}>{task.versions.filter(v=>v.status==='completed').map((v,i)=><option key={v.id} value={v.id}>V{i+1} · {v.goal}</option>)}</select></label>}</div>}
        {pending&&<SpectrumImportConfirmation inspection={pending.inspection} busy={busy} txt={txt} onConfirm={index=>upload(pending.file,true,index)} onCancel={()=>setPending(null)}/>}
        {source&&<div className="sg-selected-source"><strong>{source.name}</strong><PeakFitChart result={{wavenumber:source.spectrum.wavenumber,observed:source.spectrum.intensity}} compact dark={theme==='dark'} txt={txt} onPick={picking?e=>{const x=e.points?.[0]?.x;if(Number.isFinite(x)&&x>=Number(start)&&x<=Number(end))addPeak(x);}:undefined}/>
          <label className="sg-checkbox"><input type="checkbox" checked={baseline} disabled={locked||hasBaseline(source.steps)} onChange={e=>{setBaseline(e.target.checked);setDirty(true);}}/>{hasBaseline(source.steps)?txt('所选处理版本已包含基线校正','The selected version includes baseline correction'):txt('确认该光谱已完成基线校正','Confirm this spectrum is already baseline-corrected')}</label>
          <label className="sg-checkbox"><input type="checkbox" checked={units} disabled={locked} onChange={e=>{setUnits(e.target.checked);setDirty(true);}}/>{txt('确认横轴为拉曼位移 cm⁻¹','Confirm Raman shift in cm⁻¹')}</label>
          <ModuleInputActions api={api} module="peak-fitting" source={source} txt={txt} disabled={locked} onError={setError}/><details><summary>{txt('导入检查','Import report')}</summary><ImportReport metadata={source.metadata}/></details></div>}
        <button className="sg-text-link" disabled={locked} onClick={example}>{txt('载入三峰模拟示例','Load simulated three-peak example')}<ArrowRight size={13}/></button><p className="sg-help">{txt('模拟示例用于熟悉操作，不是实测样品。拟合不会自动扣基线或插值。','The simulated example demonstrates the controls and is not an experimental sample. Fitting does not subtract a baseline or interpolate.')}</p>
      </section>
      <section className="sg-panel"><div className="sg-panel-heading"><h2><span>02</span>{txt('拟合区间与分峰设置','Range & peak settings')}</h2><span className="sg-pill">{peaks.length} / 12</span></div>
        <div className="pf-field-grid"><label>{txt('起始波数','Start wavenumber')}<input aria-label={txt('起始波数','Start wavenumber')} type="number" value={start} disabled={locked||!source} onChange={e=>{setStart(e.target.value);setDirty(true);}}/></label><label>{txt('终止波数','End wavenumber')}<input aria-label={txt('终止波数','End wavenumber')} type="number" value={end} disabled={locked||!source} onChange={e=>{setEnd(e.target.value);setDirty(true);}}/></label></div>
        <p className="sg-help">{txt('根据峰顶、肩峰、不对称形状及参考谱设置峰数和初值。隐藏峰需要先验依据；可调整峰数和初值，多次比较残差及参数稳定性。','Use maxima, shoulders, asymmetry and reference spectra to choose peaks and initial values. Hidden peaks require prior evidence. Compare residuals and parameter stability across multiple fits.')}</p>
        {peaks.map((p,index)=><article className="pf-peak-editor" key={index}><header><strong>{txt('分峰','Peak')} {index+1}</strong><button aria-label={`${txt('删除分峰','Remove peak')} ${index+1}`} disabled={locked||peaks.length===1} onClick={()=>{setPeaks(old=>old.filter((_,i)=>i!==index));setDirty(true);}}><Trash2 size={14}/></button></header>
          <label>{txt('峰形','Profile')}<select aria-label={`${txt('分峰','Peak')} ${index+1} ${txt('峰形','Profile')}`} value={p.shape} disabled={locked} onChange={e=>edit(index,'shape',e.target.value)}><option value="voigt">Voigt</option><option value="gaussian">{txt('高斯（η = 0，固定）','Gaussian (η = 0, fixed)')}</option><option value="lorentzian">{txt('洛伦兹（η = 1，固定）','Lorentzian (η = 1, fixed)')}</option></select></label>
          <div className="pf-field-grid">{number(index,'center',txt('初始峰位','Initial center'))}{number(index,'width',txt('初始宽度参数','Initial width'),{min:0})}</div>
          <details><summary>{txt('初值与约束','Initial values & bounds')}</summary><p className="sg-help">{txt('下限 = 上限 = 初值时固定该参数；峰面积留空时由峰高和宽度估计初值，必须为正。','Equal lower bound, upper bound and initial value fix a parameter. Blank area uses a height/width estimate; peak area must be positive.')}</p>
            <div className="pf-field-grid">{number(index,'center_min',txt('峰位下限','Center lower'))}{number(index,'center_max',txt('峰位上限','Center upper'))}{number(index,'width_min',txt('宽度下限','Width lower'),{min:0})}{number(index,'width_max',txt('宽度上限','Width upper'),{min:0})}{number(index,'area',txt('初始面积（自动）','Initial area (auto)'),{min:0})}{number(index,'area_min',txt('面积下限','Area lower'),{min:0})}{number(index,'area_max',txt('面积上限（不限）','Area upper (unbounded)'),{min:0})}</div>
            {p.shape==='voigt'&&<div className="pf-field-grid">{number(index,'eta',txt('初始 η','Initial η'),{min:0,max:1})}{number(index,'eta_min',txt('η 下限','η lower'),{min:0,max:1})}{number(index,'eta_max',txt('η 上限','η upper'),{min:0,max:1})}</div>}
          </details></article>)}
        <div className="pf-actions"><button disabled={locked||!source||peaks.length>=12} onClick={()=>addPeak()}><Plus size={15}/>{txt('添加分峰','Add peak')}</button><button disabled={locked||!source||peaks.length>=12} aria-pressed={picking} onClick={()=>setPicking(v=>!v)}><MousePointer2 size={15}/>{picking?txt('点击上方光谱选择峰位','Click the input chart to select a center'):txt('图上选峰','Pick on chart')}</button></div>
        <button className="sg-primary pf-run" disabled={locked||!source||!baseline||!units||!peaks.length||!Number.isFinite(Number(start))||!Number.isFinite(Number(end))||Number(start)>=Number(end)} onClick={run}>{active||busy?<Loader2 size={17} className="sg-spin"/>:<ChartNoAxesCombined size={17}/>} {active?txt('正在拟合…','Fitting…'):txt('开始拟合','Fit peaks')}</button>
        {source&&(!baseline||!units)&&<p className="sg-help">{txt('请先完成基线校正，并确认光谱状态及横轴单位。','Complete baseline correction and confirm the spectrum status and axis units first.')}</p>}
      </section>
    </div><section className="sg-panel pf-results" ref={resultRef}><div className="sg-panel-heading"><h2><span>03</span>{txt('拟合结果','Fit results')}</h2>{complete&&<FileExport txt={txt} actions={['parameters','curves','png','bundle'].map((kind,i)=>({label:[txt('参数 CSV','Parameters CSV'),txt('全部曲线 TSV','All curves TSV'),txt('拟合图 PNG','Fit figure PNG'),txt('完整结果 ZIP','Complete result ZIP')][i],run:()=>download(kind)}))}/>}</div>
      <SavedAnalysisRecords api={api} module="peak-fitting" job={job} txt={txt} disabled={locked} onError={setError}/>
      {dirty&&complete&&<p className="pf-warning">{txt('参数已修改。当前图表仍为上次拟合结果，请重新拟合比较。','Settings have changed. The chart shows the previous fit; fit again to compare.')}</p>}
      {complete?<PeakFitResult result={job.result} dark={theme==='dark'}/>:<div className="pf-empty"><ChartNoAxesCombined size={44}/><h3>{active?txt('拟合正在进行','Fit in progress'):txt('等待拟合','Ready for your spectrum')}</h3><p>{txt('拟合完成后显示各分峰、总拟合、残差和参数，并自动记录。','Components, total fit, residuals and parameters appear here and are saved automatically.')}</p></div>}
    </section></div>
  </div>;
}
