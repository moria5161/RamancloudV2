import { usePreferences } from '../i18n';
import { systemText } from '../locale.js';
import React, {useEffect, useRef, useState} from 'react';
import {Download, Loader2} from 'lucide-react';
import {Modal} from './ResultActions';
import {spectrumImageData} from './downloadSpectrumImage';
import {safeSpectrumStem, spectrumText} from '../spectrumExport';
import {createZip} from '../zipArchive';
import {apiErrorMessage} from '../auth';

export default function BatchSpectrumExport({api, targets, name, disabled, label, ariaLabel, txt: providedTxt}) {
  const { language } = usePreferences();
  const txt = providedTxt || ((zh, en) => language === 'zh' ? zh : en);
  const [open,setOpen] = useState(false), [refs,setRefs] = useState([]), [busy,setBusy] = useState(false);
  const [roles,setRoles] = useState({original:false,processed:true}), [formats,setFormats] = useState({txt:true,png:false});
  const [error,setError] = useState(''), [progress,setProgress] = useState(''), [done,setDone] = useState('');
  const controller = useRef();
  useEffect(() => () => controller.current?.abort(), []);
  function close() {controller.current?.abort();setOpen(false);}
  async function download() {
    const request = new AbortController(); controller.current = request;
    setBusy(true);setError('');setDone('');setProgress(txt('正在读取光谱…','Loading spectra…'));
    try {
      if (refs.length > 100) throw new Error(txt('每次最多导出 100 条光谱，请减少选择。','Select at most 100 spectra per export.'));
      const {data} = await api.post('/spectra/export-data',{spectra:refs,...roles},{signal:request.signal});
      if (!data.items.length) throw new Error(txt('所选光谱没有可导出的数据，可尝试选择原始光谱。','No exportable data. Try selecting original spectra.'));
      const entries = [], manifest = [], selectedFormats = Object.keys(formats).filter(key => formats[key]);
      const total = data.items.reduce((sum,item) => sum + ['original','processed'].filter(role => item[role]).length * selectedFormats.length,0);
      let count = 0;
      for (const [index,item] of data.items.entries()) {
        const stem = safeSpectrumStem(item.source_name), directory = `${String(index+1).padStart(3,'0')}_${stem}`;
        const files = [];
        for (const role of ['original','processed']) {
          if (!item[role]) continue;
          const processed = role === 'processed', suffix = processed ? `processed${item.version ? '_V'+item.version : ''}` : 'original';
          for (const format of selectedFormats) {
            if (request.signal.aborted) throw new DOMException('Aborted','AbortError');
            const filename = `${directory}/${stem}_${suffix}.${format}`;
            let content;
            if (format === 'txt') content = spectrumText(item[role]);
            else {
              const title = `${item.source_name || 'Spectrum'} · ${processed ? txt('处理后光谱','Processed spectrum') + (item.version ? ' V'+item.version : '') : txt('原始光谱','Original spectrum')}`;
              const url = await spectrumImageData(item[role],{title});
              content = Uint8Array.from(atob(url.slice(url.indexOf(',')+1)),char => char.charCodeAt(0));
            }
            entries.push({name:filename,data:content}); files.push(filename);
            setProgress(`${txt('正在打包','Packing')} ${++count} / ${total}`);
            await new Promise(resolve => setTimeout(resolve,0));
          }
        }
        manifest.push({source_name:item.source_name,run_id:item.run_id,workflow_id:item.workflow_id,version_id:item.version_id,version:item.version,files});
      }
      if (request.signal.aborted) throw new DOMException('Aborted','AbortError');
      entries.push({name:'manifest.json',data:JSON.stringify({spectra:manifest,skipped:data.skipped},null,2)});
      const url = URL.createObjectURL(createZip(entries));
      const link = document.createElement('a');link.href=url;link.download=`${safeSpectrumStem(name || 'raman_spectra')}_export.zip`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
      setDone(`${txt('已导出','Exported')} ${manifest.length} ${txt('条光谱','spectra')}${data.skipped.length ? txt('，未导出项见包内清单','; skipped items are listed in the archive') : ''}`);
    } catch(error) {
      if (!request.signal.aborted) setError(apiErrorMessage(error));
    } finally {setBusy(false);setProgress('');}
  }
  return <><button type="button" aria-label={ariaLabel} disabled={disabled || !targets.length} onClick={()=>{setRefs(targets.map(target=>({...target})));setOpen(true);setError('');setDone('');}}><Download size={15}/>{label || txt('批量导出','Batch export')}</button>
    {open && <Modal title={txt('批量导出光谱','Export spectra')} onClose={close}>
      <p className="result-muted">{txt('已选','Selected')} {refs.length} {txt('条光谱 · ZIP 文件','spectra · ZIP file')}</p>
      <section><h3>{txt('光谱','Spectra')}</h3><div className="result-actions-row">{[['original',txt('原始光谱','Original spectra')],['processed',txt('处理后光谱','Processed spectra')]].map(([key,label])=><label className="batch-export-option" key={key}><input type="checkbox" checked={roles[key]} disabled={busy} onChange={event=>setRoles({...roles,[key]:event.target.checked})}/>{systemText(label)}</label>)}</div></section>
      <section><h3>{txt('格式','Formats')}</h3><div className="result-actions-row">{[['txt',txt('TXT 数据','TXT data')],['png',txt('PNG 图片','PNG images')]].map(([key,label])=><label className="batch-export-option" key={key}><input type="checkbox" checked={formats[key]} disabled={busy} onChange={event=>setFormats({...formats,[key]:event.target.checked})}/>{systemText(label)}</label>)}</div></section>
      {progress && <p role="status"><Loader2 size={16} className="result-spin"/>{progress}</p>}{done && <p role="status">{done}</p>}{error && <p role="alert" className="result-error">{systemText(error)}</p>}
      <footer><button onClick={close}>{busy ? txt('停止导出','Stop export') : txt('取消','Cancel')}</button><button className="result-primary" disabled={busy || !Object.values(roles).some(Boolean) || !Object.values(formats).some(Boolean)} onClick={download}><Download size={15}/>{txt('下载 ZIP','Download ZIP')}</button></footer>
    </Modal>}
  </>;
}
