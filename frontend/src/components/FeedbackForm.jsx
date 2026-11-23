import { systemText } from '../locale.js';
import React, { useEffect, useId, useRef, useState } from 'react';
import axios from 'axios';
import { Link, useLocation } from 'react-router-dom';
import { CheckCircle2, Loader2, Send } from 'lucide-react';
import { useAuth, apiErrorMessage } from '../auth';
import { usePreferences } from '../i18n';
import { FEEDBACK_CATEGORIES, feedbackRequestId } from '../content/feedback';
import { localize } from '../content/platformGuide';
import './Feedback.css';

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '') + '/api';

export default function FeedbackForm({ onSubmitted }) {
  const { user, token } = useAuth();
  const { language } = usePreferences();
  const location = useLocation(), id = useId(), controller = useRef(null);
  const text = value => localize(value, language), txt = (zh, en) => text([zh, en]);
  const [form, setForm] = useState(() => ({ category: 'bug', title: '', body: '', request_id: feedbackRequestId() }));
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [submitted, setSubmitted] = useState(null);
  useEffect(() => () => controller.current?.abort(), []);
  function edit(field, value) { setForm(previous => ({ ...previous, [field]: value, request_id: feedbackRequestId() })); }
  async function submit(event) {
    event.preventDefault();
    if (busy || user?.role === 'admin') return;
    setError(''); setSubmitted(null); setBusy(true); controller.current = new AbortController();
    try {
      const { data } = await axios.post(BASE + '/feedback', { ...form, title: form.title.trim(), body: form.body.trim(), page_path: location.pathname }, { headers: { Authorization: `Bearer ${token}` }, signal: controller.current.signal, timeout: 15000 });
      setSubmitted(data); setForm({ category: 'bug', title: '', body: '', request_id: feedbackRequestId() });
      onSubmitted?.(data);
    } catch (err) { if (!axios.isCancel(err)) setError(apiErrorMessage(err, txt('提交失败，填写内容已保留，可重试。', 'Submission failed. Your text is retained for retry.'))); }
    finally { if (!controller.current?.signal.aborted) setBusy(false); }
  }
  if (user?.role === 'admin') return null;
  return <form className="feedback-form" onSubmit={submit} aria-label={txt('提交用户反馈', 'Submit feedback')}>

    {submitted && <div className="feedback-success" role="status"><CheckCircle2 size={18} /><div><strong>{txt('反馈已提交', 'Feedback submitted')}</strong><Link to={`/feedback?scope=mine&item=${encodeURIComponent(submitted.id)}`}>{txt('查看处理状态与回复', 'View status and replies')}</Link></div></div>}
    {error && <p className="feedback-error" role="alert">{systemText(error)}</p>}
    <fieldset disabled={busy}>
      <label htmlFor={`${id}-category`}>{txt('反馈类型', 'Category')}<select id={`${id}-category`} value={form.category} onChange={event => edit('category', event.target.value)}>{FEEDBACK_CATEGORIES.map(([key, label]) => <option key={key} value={key}>{text(label)}</option>)}</select></label>
      <label htmlFor={`${id}-title`}>{txt('标题', 'Title')}<input id={`${id}-title`} value={form.title} minLength={3} maxLength={120} required placeholder={txt('例如：上传某仪器数据时提示无法识别', 'e.g. Instrument export is not recognized')} onChange={event => edit('title', event.target.value)} /></label>
      <label htmlFor={`${id}-body`}>{txt('问题或建议', 'Issue or suggestion')}<textarea id={`${id}-body`} value={form.body} rows={5} minLength={10} maxLength={5000} required placeholder={txt("所在功能、操作步骤或报错信息（至少 10 字）", "Workflow, steps or error message (at least 10 characters)")} onChange={event => edit('body', event.target.value)} /><span className="feedback-character-count">{form.body.length} / 5000</span></label>
      <div className="feedback-form-actions"><button type="submit" className="learning-primary" disabled={busy || form.title.trim().length < 3 || form.body.trim().length < 10}>{busy ? <Loader2 size={15} className="feedback-spin" /> : <Send size={15} />}{busy ? txt('正在提交…', 'Submitting…') : txt('提交反馈', 'Submit feedback')}</button><Link to="/feedback?scope=mine" className="learning-text-link">{txt('我的反馈记录', 'My feedback')}</Link></div>
    </fieldset>
  </form>;
}
