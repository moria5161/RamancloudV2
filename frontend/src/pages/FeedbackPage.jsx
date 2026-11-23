import { systemText } from '../locale.js';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, ChevronLeft, ChevronRight, Inbox, Loader2, MessageSquare, Plus, RefreshCw, Save } from 'lucide-react';
import { apiErrorMessage, useAuth } from '../auth';
import { usePreferences } from '../i18n';
import FeedbackForm from '../components/FeedbackForm';
import { FEEDBACK_CATEGORIES, FEEDBACK_STATUSES, FEEDBACK_PAGE_KEYS } from '../content/feedback';
import { localize } from '../content/platformGuide';
import './LearningPages.css';
import '../components/Feedback.css';

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '') + '/api';

export default function FeedbackPage() {
  const { user, token } = useAuth(), { language, t } = usePreferences();
  const [search, setSearch] = useSearchParams();
  const isAdmin = user.role === 'admin', scope = isAdmin ? 'all' : 'mine';
  const selected = search.get('item') || '', selectedRef = useRef(selected);
  selectedRef.current = selected;
  const text = value => localize(value, language), txt = (zh, en) => text([zh, en]);
  const label = (items, key) => text(items.find(([value]) => value === key)?.[1] || [key, key]);
  const api = useMemo(() => axios.create({ baseURL: BASE, headers: { Authorization: `Bearer ${token}` }, timeout: 15000 }), [token]);
  const [status, setStatus] = useState(''), [category, setCategory] = useState(''), [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0), [inbox, setInbox] = useState(null), [detail, setDetail] = useState(null);
  const [listBusy, setListBusy] = useState(false), [detailBusy, setDetailBusy] = useState(false), [saving, setSaving] = useState(false);
  const [listError, setListError] = useState(''), [detailError, setDetailError] = useState(''), [message, setMessage] = useState('');
  const [draft, setDraft] = useState({ status: 'new', reply: '' });
  const [showForm, setShowForm] = useState(false);
  const dirty = detail && (draft.status !== detail.status || draft.reply !== detail.reply);
  const saveController = useRef(null);
  useEffect(() => () => saveController.current?.abort(), []);

  function openItem(id) { setSearch(id ? { scope, item: id } : { scope }); }
  useEffect(() => {
    const controller = new AbortController();
    setListBusy(true); setListError('');
    api.get('/feedback', { params: { scope, status: status || undefined, category: category || undefined, page, page_size: 20 }, signal: controller.signal })
      .then(({ data }) => {
        setInbox(data);
        if (!selectedRef.current && data.items.length) setSearch({ scope, item: data.items[0].id }, { replace: true });
      }).catch(error => { if (!axios.isCancel(error)) setListError(apiErrorMessage(error, txt('读取反馈失败，请重试。', 'Could not load feedback. Please retry.'))); })
      .finally(() => { if (!controller.signal.aborted) setListBusy(false); });
    return () => controller.abort();
  }, [api, scope, status, category, page, revision]);
  useEffect(() => {
    const controller = new AbortController();
    setDetail(null); setDetailError(''); setMessage('');
    if (!selected) { setDetailBusy(false); return; }
    setDetailBusy(true);
    api.get(`/feedback/${encodeURIComponent(selected)}`, { signal: controller.signal }).then(({ data }) => {
      setDetail(data); setDraft({ status: data.status, reply: data.reply });
    }).catch(error => { if (!axios.isCancel(error)) setDetailError(apiErrorMessage(error, txt('读取反馈详情失败。', 'Could not load this feedback.'))); })
      .finally(() => { if (!controller.signal.aborted) setDetailBusy(false); });
    return () => controller.abort();
  }, [api, selected, revision]);

  async function save(event) {
    event.preventDefault();
    if (!detail || saving || !dirty) return;
    setSaving(true); setDetailError(''); setMessage('');
    saveController.current = new AbortController();
    try {
      const { data } = await api.patch(`/feedback/${encodeURIComponent(detail.id)}`, { status: draft.status, reply: draft.reply, expected_updated_at: detail.updated_at }, { signal: saveController.current.signal });
      setDetail(data); setDraft({ status: data.status, reply: data.reply });
      setMessage(txt('处理状态与回复已保存，提交者可在自己的反馈记录中查看。', 'Status and reply saved. The submitter can view them in their feedback records.'));
      // Refresh the inbox counts without discarding the saved detail or confirmation.
      try {
        const inboxResult = await api.get('/feedback', { params: { scope, status: status || undefined, category: category || undefined, page, page_size: 20 }, signal: saveController.current.signal });
        setInbox(inboxResult.data);
      } catch (error) {
        if (!axios.isCancel(error)) setListError(txt('回复已保存，列表刷新失败，可手动刷新。', 'Reply saved, but the list could not refresh. Refresh it manually.'));
      }
    } catch (error) { if (!axios.isCancel(error)) setDetailError(apiErrorMessage(error, txt('保存失败，编辑内容已保留。', 'Save failed. Your edits are retained.'))); }
    finally { if (!saveController.current?.signal.aborted) setSaving(false); }
  }
  const date = value => value ? new Date(value).toLocaleString(language === 'zh' ? 'zh-CN' : 'en-US') : '—';
  return <div className="learning-page feedback-page"><div className="learning-container feedback-container animate-fade-in">
    <header className="feedback-header"><div><p className="learning-eyebrow"><MessageSquare size={15} />RamanCloud</p><h1>{isAdmin ? txt('反馈管理', 'Feedback management') : txt('我的反馈', 'My feedback')}</h1><p className="feedback-muted">{isAdmin ? txt("查看并回复用户反馈。", "Review and reply to feedback.") : txt("查看处理状态与回复。", "Check status and replies.")}</p></div><div className="learning-actions">{!isAdmin && <button type="button" className="learning-button" aria-expanded={showForm} aria-controls="new-feedback" onClick={() => setShowForm(!showForm)}><Plus size={15} />{txt('提交新反馈', 'New feedback')}</button>}<Link to="/tutorial#faq" className="learning-text-link"><ArrowLeft size={14} />{txt('返回常见问题', 'Back to FAQ')}</Link></div></header>
    {!isAdmin && showForm && <section className="feedback-new" id="new-feedback"><h2>{txt('提交问题或建议', 'Submit an issue or suggestion')}</h2><FeedbackForm onSubmitted={item => { setStatus(''); setCategory(''); setPage(1); openItem(item.id); setRevision(value => value + 1); setShowForm(false); }} /></section>}
    <div className="feedback-counts">{FEEDBACK_STATUSES.map(([key, title]) => <div key={key}><span>{text(title)}</span><strong>{inbox?.counts[key] ?? '—'}</strong></div>)}</div>
    <div className="feedback-toolbar"><label>{txt('处理状态', 'Status')}<select value={status} disabled={saving} onChange={event => { setStatus(event.target.value); setPage(1); openItem(''); }}><option value="">{txt('全部状态', 'All statuses')}</option>{FEEDBACK_STATUSES.map(([key, title]) => <option key={key} value={key}>{text(title)}</option>)}</select></label><label>{txt('反馈类型', 'Category')}<select value={category} disabled={saving} onChange={event => { setCategory(event.target.value); setPage(1); openItem(''); }}><option value="">{txt('全部类型', 'All categories')}</option>{FEEDBACK_CATEGORIES.map(([key, title]) => <option key={key} value={key}>{text(title)}</option>)}</select></label><button type="button" className="learning-button" disabled={listBusy || detailBusy || saving} onClick={() => setRevision(value => value + 1)}><RefreshCw size={15} />{txt('刷新', 'Refresh')}</button></div>
    <div className="feedback-layout">
      <aside className="feedback-inbox" aria-label={txt('反馈列表', 'Feedback list')}>
        {listError && <p className="feedback-error" role="alert">{systemText(listError)}</p>}
        {listBusy ? <p className="feedback-empty" role="status">{txt('正在读取反馈…', 'Loading feedback…')}</p> : inbox?.items.length ? inbox.items.map(item => <button className="feedback-list-item" key={item.id} type="button" disabled={saving} aria-pressed={selected === item.id} onClick={() => openItem(item.id)}><span className="feedback-list-meta"><span>{label(FEEDBACK_CATEGORIES, item.category)}</span><span className={`feedback-status is-${item.status}`}>{label(FEEDBACK_STATUSES, item.status)}</span></span><strong>{item.title}</strong><span className="feedback-preview">{item.preview}</span><span className="feedback-list-meta"><span>{scope === 'all' ? '@' + item.username : date(item.created_at)}</span>{item.has_reply && <span>{txt('已有回复', 'Reply available')}</span>}</span></button>) : <div className="feedback-empty"><Inbox size={25} /><p>{txt('这里还没有符合条件的反馈。', 'No feedback matches these filters.')}</p></div>}
        {!!inbox?.total && <div className="feedback-pagination"><button type="button" aria-label={txt('上一页反馈', 'Previous feedback page')} disabled={page === 1 || listBusy || saving} onClick={() => { setPage(value => value - 1); openItem(''); }}><ChevronLeft size={16} /></button><span>{page} / {Math.max(1, Math.ceil(inbox.total / 20))} · {inbox.total} {txt('条', 'items')}</span><button type="button" aria-label={txt('下一页反馈', 'Next feedback page')} disabled={page * 20 >= inbox.total || listBusy || saving} onClick={() => { setPage(value => value + 1); openItem(''); }}><ChevronRight size={16} /></button></div>}
      </aside>
      <section className="feedback-detail" aria-label={txt('反馈详情', 'Feedback detail')} aria-busy={detailBusy}>
        {detailError && <div className="feedback-error" role="alert"><p>{systemText(detailError)}</p><button type="button" className="learning-button" disabled={saving} onClick={() => setRevision(value => value + 1)}>{txt('重新载入', 'Reload')}</button></div>}
        {message && <p className="feedback-success" role="status">{systemText(message)}</p>}
        {detailBusy ? <p className="feedback-empty" role="status">{txt('正在读取详情…', 'Loading details…')}</p> : detail ? <>
          <div className="feedback-detail-heading"><span className={`feedback-status is-${detail.status}`}>{label(FEEDBACK_STATUSES, detail.status)}</span><span>{label(FEEDBACK_CATEGORIES, detail.category)}</span></div><h2>{detail.title}</h2><p className="feedback-muted">@{detail.username} · {date(detail.created_at)}</p><p className="feedback-source">{txt('来源页面', 'Source page')} <Link to={detail.page_path}>{t(FEEDBACK_PAGE_KEYS[detail.page_path] || 'homepage')}</Link></p>
          <div className="feedback-body">{detail.body}</div>
          {detail.reply && <div className="feedback-reply"><h3>{txt('管理员回复', 'Administrator reply')}</h3><p>{detail.reply}</p><small>{date(detail.replied_at)}</small></div>}
          {isAdmin ? <form className="feedback-response" onSubmit={save} aria-label={txt('管理员处理反馈', 'Administrator response')}><h3>{txt('处理与回复', 'Status & reply')}</h3><label htmlFor="feedback-status">{txt('处理状态', 'Status')}<select id="feedback-status" value={draft.status} disabled={saving} onChange={event => setDraft(previous => ({ ...previous, status: event.target.value }))}>{FEEDBACK_STATUSES.map(([key, title]) => <option key={key} value={key}>{text(title)}</option>)}</select></label><label htmlFor="feedback-reply">{txt('站内回复', 'Reply to submitter')}<textarea id="feedback-reply" rows={5} value={draft.reply} maxLength={3000} disabled={saving} onChange={event => setDraft(previous => ({ ...previous, reply: event.target.value }))} /></label><button type="submit" className="learning-primary" disabled={saving || !dirty}>{saving ? <Loader2 size={15} className="feedback-spin" /> : <Save size={15} />}{txt('保存处理结果', 'Save response')}</button></form> : !detail.reply && <p className="feedback-awaiting">{txt('管理员尚未回复，可稍后刷新查看。', 'No administrator reply yet. Refresh later for updates.')}</p>}
        </> : !detailError && <div className="feedback-empty"><MessageSquare size={27} /><p>{txt("选择一条反馈查看详情。", "Select feedback to view details.")}</p></div>}
      </section>
    </div>
  </div></div>;
}
