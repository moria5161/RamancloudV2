import { API_BASE as BASE } from '../apiBase';
import { systemText, localize } from '../locale.js';
import { usePreferences } from '../i18n';
import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { useLocation } from 'react-router-dom';
import { useAuth, apiErrorMessage } from '../auth';
import './GlobalQAAssistant.css';
import { currentQATask, screenContext } from './qaContext';
import QAAnswer from './QAAnswer.jsx';
import { plainAnswer } from './qaAnswer.js';
import { SPECTRAL_ACCEPT } from './ImportReport';
import QAPlanCard from './QAPlanCard';
import { checkPlanContext, executeQAPlan, executionInput, executionKey } from './qaExecution';
import {addPlanToTimeline,updateTimelinePlan,chatHistory} from './qaTimeline';
import { queuedRequest, queueStatus, readNDJSON } from '../queuedRequest';

const ACCEPT = SPECTRAL_ACCEPT;
const RUNNING = ['queued', 'running', 'stopping'];
export default function GlobalQAAssistant({ enabled }) {
  usePreferences();
  const { token } = useAuth();
  const location = useLocation();
  const directPreprocess = location.pathname === '/ai-analysis';
  const [open, setOpen] = useState(false), [width, setWidth] = useState(380);
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 900px)').matches);
  const [input, setInput] = useState(''), [messages, setMessages] = useState([]);
  const [spectrum, setSpectrum] = useState(null);
  const [allowAI, setAllowAI] = useState(true);
  const [busy, setBusy] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [error, setError] = useState(''), [config, setConfig] = useState(null);
  const [phase, setPhase] = useState('');
  const [includeTask, setIncludeTask] = useState(true);
  const [screen, setScreen] = useState(() => screenContext(location.pathname, false));
  const [copied, setCopied] = useState(null);
  const [plan, setPlan] = useState(null);
  const [, refreshExecution] = useState(0);
  const controller = useRef(null), epoch = useRef(0), scroll = useRef(null), mounted = useRef(true);
  const restoreController = useRef(null);
  const followTail = useRef(true);
  const headers = { Authorization: `Bearer ${token}` };
  const pageMessages = directPreprocess ? messages : messages.filter(m => m.kind !== 'plan' && !m.preprocessing);
  useEffect(() => {
    const media = window.matchMedia('(max-width: 900px)');
    const change = () => { setMobile(media.matches); setOpen(false); };
    media.addEventListener('change', change);
    return () => media.removeEventListener('change', change);
  }, []);
  useEffect(() => {
    mounted.current = true;
    const abort = new AbortController();
    axios.get(`${BASE}/assistant/config`, { headers, signal: abort.signal, timeout: 10000 })
      .then(r => setConfig(r.data.data || r.data)).catch(() => {});
    return () => { mounted.current = false; ++epoch.current; abort.abort(); controller.current?.abort(); };
  }, [token]);
  useEffect(() => { if(followTail.current)scroll.current?.scrollTo(0, scroll.current.scrollHeight); }, [messages, busy, open, enabled, directPreprocess]);
  useEffect(()=>{if(plan)setMessages(previous=>updateTimelinePlan(previous,plan));},[plan]);
  useEffect(() => {
    if (!directPreprocess) return;
    const update = () => refreshExecution(value => value + 1);
    document.addEventListener('qa-execution-input-changed', update);
    update();
    return () => document.removeEventListener('qa-execution-input-changed', update);
  }, [directPreprocess, location.search]);
  useEffect(() => {
    if (!directPreprocess) return;
    const abort=new AbortController();
    restoreController.current = abort;
    const version = epoch.current;
    axios.get(`${BASE}/qa-assistant/plans`, { headers, signal: abort.signal }).then(({ data }) => {
      if (abort.signal.aborted || version !== epoch.current || !Array.isArray(data)) return;
      const preprocessingPlans = data.filter(p => p.module === 'ai-analysis' && p.direct_preprocess);
      const restored = preprocessingPlans.find(p => RUNNING.includes(p.status)) || preprocessingPlans.find(p => p.status === 'draft');
      if (restored) {
        setPlan(restored);
        setMessages(previous => addPlanToTimeline(previous, restored, true));
      }
    }).catch(() => {});
    return()=>abort.abort();
  },[token, directPreprocess]);
  useEffect(()=>{
    if(!plan || !['queued','running','stopping'].includes(plan.status))return;
    let timer;const abort=new AbortController();
    const poll=async()=>{try{
      const {data}=await axios.get(`${BASE}/qa-assistant/plans/${plan.id}`,{headers,signal:abort.signal});
      if (abort.signal.aborted) return;
      setPlan(current => current?.id === data.id ? data : current);
      if(RUNNING.includes(data.status))timer=setTimeout(poll,1000);
    }catch(e){if(!abort.signal.aborted){setError(localize("读取方案进度失败，请刷新或检查项目权限。"));if(e.response?.status!==403&&e.response?.status!==404)timer=setTimeout(poll,3000);else setPlan(current=>current?.id===plan.id?null:current);}}};
    timer=setTimeout(poll,500);return()=>{abort.abort();clearTimeout(timer);};
  },[plan?.id,plan?.status,token]);
  useEffect(() => {
    if (!enabled) return;
    const update = () => { setScreen(previous => {
      const next = screenContext(location.pathname, false);
      return JSON.stringify({ ...previous, observed_at: '' }) === JSON.stringify({ ...next, observed_at: '' }) ? previous : next;
    }); };
    update();
    const workspace = document.querySelector('[data-qa-workspace]');
    let timer;
    const observer = new MutationObserver(() => { clearTimeout(timer); timer = setTimeout(update, 150); });
    if (workspace) observer.observe(workspace, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['data-qa-task', 'data-qa-version', 'data-qa-run', 'data-qa-state'] });
    return () => { clearTimeout(timer); observer.disconnect(); };
  }, [enabled, location.pathname, location.search]);

  async function copy(message, id) {
    try { await navigator.clipboard.writeText(message); setCopied(id); }
    catch { setError(localize("复制失败，请选中回答文字手动复制。")); }
  }
  function stop() { ++epoch.current; controller.current?.abort(); setBusy(false); }

  async function clear() {
    if (clearing) return;
    const version = ++epoch.current;
    controller.current?.abort();
    setBusy(false);
    followTail.current = true;
    setInput(''); setError('');
    setCopied(null);
    if (!directPreprocess) {
      setMessages(previous => previous.filter(m => m.kind === 'plan' || m.preprocessing));
      return;
    }
    setSpectrum(null);
    restoreController.current?.abort();
    setClearing(true);
    const activePlan = RUNNING.includes(plan?.status) ? plan : null;
    setMessages(activePlan ? addPlanToTimeline([], activePlan) : []);
    if (!activePlan) setPlan(null);
    try {
      const response = await fetch(`${BASE}/qa-assistant/plans/drafts`, {
        method: 'DELETE', headers, keepalive: true, signal: AbortSignal.timeout?.(10000),
      });
      if (!response.ok) throw new Error('Draft discard failed');
    } catch {
      if (version === epoch.current && mounted.current) setError(localize('消息已清空，旧草案清除失败。请再次点击「清空对话」。'));
    } finally {
      if (version === epoch.current && mounted.current) setClearing(false);
    }
  }
  function getRunContext() {
    const selected = includeTask ? executionInput(location.pathname) : null;
    const context = selected?.module === 'ai-analysis' ? selected : null;
    if (!spectrum) return context;
    if (context?.inputs?.source) {
      throw new Error(localize('当前页面和助手附件都有输入，请移除附件，或关闭“跟随当前页面”后使用附件。'));
    }
    return { module: 'ai-analysis', inputs: context?.inputs || {}, files: [spectrum], locked: !!context?.locked };
  }
  async function preprocess(mode) {
    const preset = mode === 'preset';
    const text = preset ? localize('一键预处理') : input.trim();
    if (!directPreprocess || busy || clearing || preprocessingBlocker || (!preset && (!text || !allowAI))) return;
    const version = ++epoch.current;
    const abort = new AbortController();
    controller.current = abort;
    const current = () => version === epoch.current && mounted.current;
    const history = chatHistory(messages).filter(m => m.preprocessing).slice(-6)
      .map(({ role, content }) => ({ role, content: content.slice(0, 3000) }));
    followTail.current = true;
    setError('');
    setBusy(true);
    setPhase(localize(preset ? '正在准备一键预处理…' : '正在识别所需的预处理步骤…'));
    if (!preset) {
      setInput('');
      setMessages(previous => [...previous, { role: 'user', content: text, preprocessing: true, attachments: [spectrum?.name].filter(Boolean) }]);
    }
    let draft;
    try {
      const context = getRunContext();
      const context_key = await executionKey(context);
      if (!current()) return;
      const form = new FormData();
      form.append('payload', JSON.stringify({ module: 'ai-analysis', mode, goal: text, history: preset ? [] : history,
        allow_ai: allowAI, context_key, inputs: context.inputs,
        parent_plan_id: plan?.context_key === context_key ? plan.id : undefined }));
      if (spectrum) form.append('spectrum', spectrum);
      const data = await queuedRequest(BASE + '/qa-assistant/preprocessing-turn',
        { headers, body: form, signal: abort.signal }, event => {
          if (current()) setPhase(event.type === 'queued' ? queueStatus(event.ahead) : localize('正在识别所需的预处理步骤…'));
        });
      if (!current()) return;
      if (data.kind === 'clarification') {
        setMessages(previous => [...previous, { role: 'assistant', content: data.answer, clarification: true, preprocessing: !preset }]);
        return;
      }
      if (!data.plan?.id) throw new Error(localize('生成方案失败，请重试。'));
      draft = data.plan;
      if (preset && !draft.needs_units && !draft.needs_sharing) {
        setPhase(localize('正在提交…'));
        await checkPlanContext(getRunContext(), draft);
        if (!current()) return;
        draft = await executeQAPlan(BASE, draft, headers, { signal: abort.signal });
      }
      if (!current()) return;
      setPlan(draft);
      setMessages(previous => addPlanToTimeline(previous, draft));
    } catch (err) {
      if (current() && err.name !== 'AbortError' && !axios.isCancel(err)) {
        if (!preset) setInput(text);
        if (draft) {
          setPlan(draft);
          setMessages(previous => addPlanToTimeline(previous, draft));
        }
        setError(err.response ? apiErrorMessage(err) : err.message || localize('生成方案失败，请重试。'));
      }
    } finally {
      if (current()) setBusy(false);
    }
  }
  async function send(e) {
    e.preventDefault();
    if (busy || clearing || !input.trim() || !allowAI) return;
    const version = ++epoch.current, text = input.trim();
    const attachment = directPreprocess ? spectrum : null;
    const history = chatHistory(pageMessages).slice(-6).map(({ role, content }) => ({ role, content: content.slice(0, 3000) }));
    const form = new FormData(); form.append('message', text);
    form.append('history', JSON.stringify(history));
    const context = includeTask ? screenContext(location.pathname) : { path: location.pathname };

    form.append('allow_ai', 'true'); form.append('page_context', JSON.stringify(context));
    const currentTask = includeTask ? currentQATask() : null;
    if (currentTask?.run_id) form.append('run_id', currentTask.run_id);
    else if (currentTask) { form.append('task_id', currentTask.task_id); form.append('version_id', currentTask.version_id); }
    form.append('stream', 'true');
    if (directPreprocess && plan && (includeTask || attachment)) form.append('action_plan_id', plan.id);
    if (attachment) form.append('spectrum', attachment);

    controller.current = new AbortController(); setBusy(true); setInput(''); setError('');
    setPhase(localize(attachment ? '正在校验附件和读取任务…' : '正在读取当前输入…'));
    const signal = controller.current.signal;
    followTail.current=true;
    const replyId = crypto.randomUUID();
    setMessages(previous => [...previous, { role: 'user', content: text, attachments: attachment ? [attachment.name] : [] }, { id: replyId, role: 'assistant', content: '', incomplete: true, contextLabel: includeTask ? `${context.page}${localize(" · 提问时状态")}` : '' }]);
    try {
      const response = await fetch(`${BASE}/qa-assistant/reply`, { method: 'POST', body: form, headers, signal });
      if (!response.ok) { const body = await response.json(); throw new Error(typeof body.detail === 'string' ? body.detail : localize("请求失败")); }
      if (response.headers.get('content-type')?.includes('application/json')) {
        const raw = await response.json(), answer = raw.data || raw;
        if (version !== epoch.current || !mounted.current) return;
        if (!answer.answer) throw new Error(localize("模型未返回回答，请重试。"));
        setMessages(previous => previous.map(m => m.id === replyId ? { ...m, content: answer.answer, incomplete: false,
          sources: answer.sources, warnings: answer.warnings, evidence: answer.evidence } : m));
        return;
      }
      let complete = false, received = false;
      const update = changes => { if (version === epoch.current && mounted.current) setMessages(previous => previous.map(m => m.id === replyId ? { ...m, ...changes, content: changes.delta !== undefined ? m.content + changes.delta : m.content } : m)); };
      await readNDJSON(response, item => {
        if (item.type === 'status') setPhase(item.message);
        if (item.type === 'queued') setPhase(queueStatus(item.ahead));
        if (item.type === 'running') setPhase(localize('正在生成回答'));
        if (item.type === 'metadata') update({ provider: item.provider, model: item.model, warnings: item.warnings, evidence: item.evidence, sources: item.sources, summary: item.attachment_summary });
        if (item.type === 'delta') { received = true; update({ delta: item.text }); setPhase(localize("正在输出回答…")); }
        if (item.type === 'done') { complete = true; update({ incomplete: !!item.truncated, truncated: !!item.truncated }); }
      });
      if (!complete || !received) throw new Error(localize("回答不完整，请重试。"));
      if (version !== epoch.current || !mounted.current) return;
    } catch (err) {
      if (version === epoch.current && mounted.current && err.name !== 'AbortError' && !axios.isCancel(err)) {
        setInput(text);
        setError(err.response ? apiErrorMessage(err) : (err.code === 'ECONNABORTED' ? localize("模型响应超时，内容和附件已保留，请重试。") : err.message || localize("发送失败，请重试")));
      }
    } finally { if (version === epoch.current && mounted.current) setBusy(false); }
  }
  function resize(e) {
    e.currentTarget.setPointerCapture(e.pointerId);
    const origin = e.clientX, initial = width;
    e.currentTarget.onpointermove = event => setWidth(Math.max(320, Math.min(600, initial + origin - event.clientX)));
    e.currentTarget.onpointerup = event => { event.currentTarget.onpointermove = null; };
    e.currentTarget.onpointercancel = event => { event.currentTarget.onpointermove = null; };
  }
  if (!enabled) return null;

  let preprocessingBlocker = '';
  if (directPreprocess) {
    let runContext, contextError;
    try { runContext = getRunContext(); } catch (e) { contextError = e.message; }
    if (RUNNING.includes(plan?.status)) preprocessingBlocker = localize('请等待当前方案结束，或先停止方案。');
    else if (contextError) preprocessingBlocker = contextError;
    else if (runContext?.locked) preprocessingBlocker = localize('请等待当前模块处理或导入完成');
    else if (runContext?.inputs?.batch_id && !runContext.inputs.workflow_ids?.length) preprocessingBlocker = localize('请先勾选需要批量处理的数据');
    else if (!spectrum && !runContext?.inputs?.source) preprocessingBlocker = localize('请先上传或选择要处理的光谱。');
  }
  const preprocessingHint = preprocessingBlocker || (!allowAI
    ? localize('允许 AI 读取附带数据后可生成自定义方案。')
    : localize('点击「发送」提问，或描述处理要求后点击「生成预处理方案」。'));
  if (mobile && !open) return <button className="qa-launch" onClick={() => setOpen(true)} aria-label={localize("打开 AI 问答助手")}>{localize("AI 问答")}</button>;
  return <aside data-qa-assistant className="qa-panel" style={{ '--qa-width': `${width}px` }} aria-label={localize("AI 问答助手")}>
    <div className="qa-resize" role="separator" tabIndex={0} aria-label={localize("调整助手宽度")} aria-orientation="vertical" onPointerDown={resize} onKeyDown={e => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); setWidth(w => Math.max(320, Math.min(600, w + (e.key === 'ArrowLeft' ? 20 : -20)))); } }} />
    <header><div><strong>{localize("AI 问答助手")}</strong><small title={config?.model || ''}>{localize("光谱专业问答")}{config?.provider === 'ollama' ? localize(" · 本地模型") : ''}</small></div><div className="qa-header-actions"><button onClick={clear} disabled={clearing} title={localize(directPreprocess ? '清空对话、附件和未运行草案' : '清空对话')}>{localize("清空对话")}</button>{mobile && <button onClick={() => setOpen(false)} aria-label={localize("收起 AI 问答助手")}>{localize("收起")}</button>}</div></header>
    <div className="qa-messages" ref={scroll} aria-live="polite" onScroll={e=>{const el=e.currentTarget;followTail.current=el.scrollHeight-el.scrollTop-el.clientHeight<80;}}>
      {!pageMessages.length && <div className="qa-welcome"><strong>{localize("边操作，边提问")}</strong><p>{localize("我会跟随当前页面，结合你的任务解答。")}</p><div className="qa-suggestions">{[localize("下一步该怎么操作？"), localize("帮我解读当前结果")].map(text => <button key={text} onClick={() => setInput(text)}>{text}</button>)}</div></div>}
      {pageMessages.map((m, i) => m.kind==='plan' ? <QAPlanCard key={m.id} plan={m.plan} onPlan={next=>{setMessages(previous=>updateTimelinePlan(previous,next));setPlan(current=>current?.id===next.id?next:current);}} base={BASE} headers={headers} getContext={getRunContext} onRevise={setInput} /> : <article className={`qa-message qa-${m.role}`} key={m.id || i}><strong>{m.role === 'user' ? localize("我") : localize("AI 助手")}</strong><>{m.role === 'assistant' ? <QAAnswer text={m.clarification ? systemText(m.content) : m.content} /> : <p>{m.content}</p>}</>{m.incomplete && !busy && <small className="qa-warning">{m.truncated ? localize("已达到本次回答长度上限，可继续回答。") : localize("回答未完成，已保留生成的文字，可重试。")}</small>}{m.truncated && !busy && <button className="qa-copy" onClick={() => setInput(localize("请接着上一条回答继续，从未完成处开始，不要重复已有内容。"))}>{localize("继续回答")}</button>}{m.attachments?.map(name => <small key={name}>{localize("附件：")}{name}</small>)}{(m.sources || []).length > 0 && <details className="qa-sources"><summary>{localize("回答依据")}</summary>{m.contextLabel && <small>{systemText(m.contextLabel)}</small>}{m.sources.map(s => <small key={s.id}>[{s.id}] {systemText(s.label)}</small>)}</details>}{(Array.isArray(m.warnings) ? m.warnings : m.warnings ? [m.warnings] : []).map((w, n) => <small className="qa-warning" key={n}>{systemText(String(w))}</small>)}{m.role === 'assistant' && !m.incomplete && <button className="qa-copy" onClick={() => copy(plainAnswer(m.content), m.id || i)}>{copied === (m.id || i) ? localize("已复制") : localize("复制回答")}</button>}</article>)}
      {busy && <p className="qa-status" role="status">{systemText(phase)}</p>}
    </div>
    <form onSubmit={send} className="qa-composer">
      {error && <p className="qa-error" role="alert">{systemText(error)}</p>}
      {directPreprocess && <>
        {spectrum && <div className="qa-attachment"><span>{spectrum.name}</span><button type="button" disabled={busy} onClick={() => setSpectrum(null)} aria-label={localize("移除光谱附件")}>{localize("移除")}</button></div>}
        <div className="qa-tools">
          <label className="qa-upload">{localize("上传光谱")}<input aria-label={localize("上传光谱数据")} type="file" accept={ACCEPT} disabled={busy} onChange={e => {
            const file = e.target.files?.[0]; e.target.value = ''; if (!file) return;
            if (file.size > 4 * 1024 * 1024) { setError(localize("光谱文件不能超过 4MB")); return; }
            if (!ACCEPT.split(',').includes('.' + file.name.split('.').at(-1).toLowerCase())) { setError(localize("不支持该文件格式，请选择光谱数据文件")); return; }
            setSpectrum(file); setError('');
          }} /></label>
          <button type="button" className="qa-quick-preprocess" disabled={busy || clearing || !!preprocessingBlocker}
            title={preprocessingBlocker || localize('对所选光谱依次运行 despike、F2P 和 AirNet')}
            aria-describedby="qa-plan-readiness" onClick={() => preprocess('preset')}>{localize('一键预处理')}</button>
        </div>
        <small id="qa-plan-readiness" className="qa-plan-readiness" role="status">{preprocessingHint}</small>
      </>}
      <label className="qa-task-context" title={localize("本地跟随页面状态；发送问题时读取最新的参数、进度与结果摘要，不截屏、不操作任务。")}><input type="checkbox" checked={includeTask} disabled={busy} onChange={e => setIncludeTask(e.target.checked)} />{localize("跟随当前页面")}<span>{!includeTask ? localize("已暂停") : localize(screen.page)}{includeTask && screen.state?.status ? ` · ${{completed:localize("已完成"),running:localize("运行中"),queued:localize("排队中"),failed:localize("失败"),draft:localize("待确认"),preview:localize("已预览"),previewing:localize("预览中"),loaded:localize("已加载"),empty:localize("待上传"),cancelled:localize("已停止")}[screen.state.status] || screen.state.status}` : ''}</span></label>
      <textarea aria-label={localize("问答消息")} placeholder={localize(directPreprocess ? '输入消息或描述预处理要求…' : '输入消息…')} value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') send(e); }} maxLength={6000} disabled={busy} rows={3} />
      <label className="qa-consent" title={directPreprocess ? localize("允许已配置的模型读取本次问题及附带数据，可随时取消。") : undefined}><input type="checkbox" checked={allowAI} onChange={e => setAllowAI(e.target.checked)} disabled={busy} />{localize(directPreprocess ? '允许 AI 读取附带数据' : '允许 AI 读取问题和页面上下文')}</label>
      <div className="qa-compose-footer qa-bottom-actions">
        {directPreprocess && <button type="button" className="qa-create-plan" disabled={busy || clearing || !!preprocessingBlocker || !allowAI || !input.trim()}
          aria-describedby="qa-plan-readiness" onClick={() => preprocess('custom')}>{localize('生成预处理方案')}</button>}
        {busy ? <button className="qa-send" type="button" onClick={stop}>{localize("停止生成")}</button>
          : <button className="qa-send" type="submit" disabled={clearing || !allowAI || !input.trim()}>{localize("发送")}</button>}
      </div>
      <small className="qa-footnote">{localize("回答供参考 · 对话仅在本次会话保留")}</small>
    </form>
  </aside>;
}
