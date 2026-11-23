import { API_BASE as BASE } from '../apiBase';
import { systemText } from '../locale.js';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { Bot, Check, History, Loader2, RotateCcw, Send, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiErrorMessage, useAuth } from '../auth';
import { usePreferences } from '../i18n';
import './AIChatPanel.css';


export default function AIChatPanel({ surface, context = {}, onApplyCommand, blocked = false }) {
  const { token } = useAuth();
  const { language } = usePreferences();
  const txt = (zh, en) => language === 'zh' ? zh : en;
  const api = useMemo(() => axios.create({ baseURL: BASE, headers: { Authorization: `Bearer ${token}` }, timeout: 190000 }), [token]);
  const [config, setConfig] = useState(null);
  const [conversation, setConversation] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState('loading');
  const [error, setError] = useState('');
  const [allowAI, setAllowAI] = useState(false);
  const epoch = useRef(0);
  const scroll = useRef(null);
  const controller = useRef(null);
  const signature = JSON.stringify(context);
  const live = useRef(signature);
  live.current = signature;
  const sourceKey = JSON.stringify([surface, context.raw_dataset_id, context.mode, context.raw_wavenumber, context.raw_intensity]);

  useEffect(() => {
    const version = ++epoch.current;
    const abort = new AbortController();
    controller.current = abort;
    setBusy('loading'); setError(''); setConversation(null); setMessages([]); setPending(null); setInput(''); setAllowAI(false);
    async function load() {
      try {
        const [settings, opened] = await Promise.all([
          api.get('/assistant/config', { signal: abort.signal, timeout: 10000 }),
          api.post('/assistant/conversations', { surface, context }, { signal: abort.signal, timeout: 15000 }),
        ]);
        if (version !== epoch.current) return;
        setConfig(settings.data); setConversation(opened.data.id); setMessages(opened.data.messages);
        const last = opened.data.messages.at(-1);
        if (last?.command?.requires_confirmation && !last.applied && last.snapshot === opened.data.snapshot) {
          setPending({ ...last.command, messageId: last.id, signature: live.current });
        }
      } catch (err) {
        if (version === epoch.current && !axios.isCancel(err)) setError(apiErrorMessage(err));
      } finally {
        if (version === epoch.current) setBusy('');
      }
    }
    load();
    return () => { ++epoch.current; abort.abort(); };
    // Source changes open their own server-side conversation; edits keep the thread.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, surface, sourceKey]);

  useEffect(() => {
    if (pending && pending.signature !== signature && busy !== 'applying') {
      setPending(null);
      setError(txt('数据或参数已变化，请重新生成处理建议。', 'Data or parameters changed. Request a new plan.'));
    }
  }, [signature, pending, busy, language]);

  useEffect(() => {
    if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [messages, busy, pending]);

  async function send(event) {
    event?.preventDefault();
    const text = input.trim();
    if (!text || busy || blocked || !conversation) return;
    const version = epoch.current;
    const snapshot = live.current;
    setBusy('sending'); setError(''); setInput(''); setPending(null);
    try {
      const result = (await api.post('/assistant/chat', { conversation_id: conversation, surface, context, message: text, language, allow_ai: allowAI },
        { signal: controller.current.signal, timeout: config?.provider === 'ollama' ? 330000 : 65000 })).data;
      if (version !== epoch.current) return;
      setMessages(result.messages);
      if (result.reply.command?.requires_confirmation && snapshot === live.current && onApplyCommand) {
        setPending({ ...result.reply.command, messageId: result.reply.id, signature: snapshot });
      } else if (snapshot !== live.current) {
        setError(txt('回答基于发送时的数据；当前数据已变化。', 'This answer describes the data at send time; the workspace has changed.'));
      }
    } catch (err) {
      if (version === epoch.current && !axios.isCancel(err)) { setError(apiErrorMessage(err)); setInput(text); }
    } finally {
      if (version === epoch.current) setBusy('');
    }
  }

  async function clear() {
    if (busy || blocked || !conversation || !window.confirm(txt('清空当前数据的对话记录？', 'Clear this conversation?'))) return;
    const version = epoch.current;
    setBusy('clearing'); setError('');
    try {
      await api.delete(`/assistant/conversations/${conversation}`, { signal: controller.current.signal });
      if (version === epoch.current) { setMessages([]); setPending(null); }
    } catch (err) { if (version === epoch.current && !axios.isCancel(err)) setError(apiErrorMessage(err)); }
    finally { if (version === epoch.current) setBusy(''); }
  }

  async function apply() {
    if (!pending || busy || blocked || pending.signature !== live.current) return;
    const version = epoch.current;
    setBusy('applying'); setError('');
    let saved = false;
    try {
      const run = await onApplyCommand(pending);
      saved = true;
      if (version !== epoch.current) return;
      setPending(null);
      if (!run?.id) throw new Error(txt('处理已完成，但没有返回保存记录。', 'Processing completed without a saved history record.'));
      const result = (await api.post(`/assistant/conversations/${conversation}/applied`, { message_id: pending.messageId, analysis_run_id: run.id },
        { signal: controller.current.signal, timeout: 15000 })).data;
      if (version === epoch.current) setMessages(result.messages);
    } catch (err) {
      if (version === epoch.current) {
        if (saved) setPending(null);
        setError((saved ? txt('结果已处理，对话记录更新失败：', 'Processing completed, but chat logging failed: ') : '') + apiErrorMessage(err));
      }
    } finally { if (version === epoch.current) setBusy(''); }
  }

  return <section className="assistant-chat" aria-label={txt('AI 对话', 'AI Chat')}>
    <header className="assistant-header">
      <div className="assistant-heading"><Bot size={18} /><div><strong>{txt('AI 对话', 'AI Chat')}</strong><small>{config ? `${config.provider_name} · ${config.model}` : txt('正在连接', 'Connecting')}</small>{config?.provider === 'ollama' && <small>{config.available ? txt('本地模型已就绪', 'Local model ready') : config.availability === 'model_missing' ? txt('模型尚未下载', 'Model not downloaded') : txt('Ollama 尚未启动', 'Ollama is offline')}</small>}</div></div>
      <button type="button" className="assistant-icon" onClick={clear} disabled={!!busy || blocked || !messages.length} title={txt('清空对话', 'Clear conversation')} aria-label={txt('清空对话', 'Clear conversation')}><RotateCcw size={16} /></button>
    </header>
    <div className="assistant-messages" ref={scroll} aria-live="polite">
      {!messages.length && !busy && <p className="assistant-empty">{txt('你好。', 'Hello.')}</p>}
      {messages.map(message => <article key={message.id} className={`assistant-message ${message.role}`}>
        <div className="assistant-message-meta"><span>{message.role === 'user' ? txt('你', 'You') : message.provider === 'local_rules' ? txt('本地规则', 'Local rules') : message.model || txt('助手', 'Assistant')}</span></div>
        <div className="assistant-content">{message.content}</div>
        {message.fallback_reason && <small className="assistant-note">{message.fallback_reason}</small>}
        {message.applied && <Link className="assistant-history" to="/analysis-history"><History size={13} />{txt('已执行并保存', 'Executed and saved')}</Link>}
      </article>)}
      {!!busy && <div className="assistant-status" role="status"><Loader2 size={15} className="animate-spin" />{busy === 'loading' ? txt('加载对话', 'Loading chat') : busy === 'applying' ? txt('执行并保存', 'Executing and saving') : txt('正在处理', 'Working')}</div>}
      {error && <div className="assistant-error" role="alert">{systemText(error)}</div>}
      {pending && <section className="assistant-plan" aria-label={txt('待确认方案', 'Pending plan')}>
        <strong>{txt('待确认方案', 'Pending plan')} · {pending.mode === 'append' ? txt('追加', 'Append') : txt('替换', 'Replace')}</strong>
        <ol>{pending.steps.map((step, index) => <li key={index}>{systemText(step.label || step.method)}<small>{Object.entries(step.params || {}).map(([key, value]) => `${key}=${value}`).join(', ')}</small></li>)}</ol>
        {surface === 'hyperspectral' && <p>{txt('作用范围：整个数据集', 'Scope: entire dataset')}</p>}
        {pending.reason && <p>{systemText(pending.reason)}</p>}
        {pending.warnings?.map((warning, i) => <small key={i}>{systemText(warning)}</small>)}
        <div className="assistant-plan-actions"><button type="button" onClick={() => setPending(null)} disabled={!!busy || blocked}><X size={14} />{txt('取消', 'Cancel')}</button><button type="button" onClick={apply} disabled={!!busy || blocked}><Check size={14} />{txt('确认执行并保存', 'Confirm and save')}</button></div>
      </section>}
    </div>
    <form onSubmit={send} className="assistant-compose">
      <label className="assistant-consent"><input type="checkbox" checked={allowAI} disabled={!!busy || blocked} onChange={e => setAllowAI(e.target.checked)} />{config?.provider === 'ollama' ? txt('允许本地 Ollama 模型读取数据摘要和对话', 'Allow the local Ollama model to read summaries and conversation') : txt('允许向模型发送数据摘要和对话内容', 'Allow model access to summaries and conversation')}</label>
      <div className="assistant-input"><textarea aria-label={txt('对话消息', 'Chat message')} value={input} maxLength={2000} rows={3} placeholder={txt('输入消息…', 'Message...')} disabled={!!busy || blocked || !conversation} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }} /><button type="submit" className="assistant-icon assistant-send" disabled={!!busy || blocked || !input.trim() || !conversation} title={txt('发送消息', 'Send message')} aria-label={txt('发送消息', 'Send message')}><Send size={17} /></button></div>
    </form>
  </section>;
}
