import { API_BASE as BASE } from '../apiBase';
import { systemText, getLocale } from '../locale.js';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Check, LogOut, RefreshCw, Send, Trash2, UserMinus, Users, X } from 'lucide-react';
import { apiErrorMessage, useAuth } from '../auth';
import { usePreferences } from '../i18n';
import './ProjectCollaboration.css';

const actions = { invite: '发出邀请', accept_invitation: '接受邀请', decline_invitation: '拒绝邀请', revoke_invitation: '撤销邀请', change_role: '变更角色', leave: '退出项目', remove_member: '移除成员', transfer: '转让所有权', publish_result: '发布结果', unpublish_result: '撤下结果', create_project: '创建项目', update_project: '更新项目', upload_dataset: '上传数据', delete_dataset: '删除数据', download_dataset: '下载数据', download_result: '下载结果' };
actions.warehouse_result = '保存结果到处理后仓库';
actions.withdraw_warehouse = '从处理后仓库移除结果';
function useProjectApi() {
  const { token, user } = useAuth();
  const { language } = usePreferences();
  return { api: useMemo(() => axios.create({ baseURL: BASE, headers: { Authorization: `Bearer ${token}` } }), [token]), user, txt: (zh, en) => language === 'zh' ? zh : en };
}

export function ProjectInvitations({ onChanged }) {
  const { api, txt } = useProjectApi();
  const [items, setItems] = useState([]), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const load = useCallback(async () => { try { setItems((await api.get('/project-invitations')).data.invitations); setError(''); } catch (e) { setError(apiErrorMessage(e)); } }, [api]);
  useEffect(() => { load(); }, [load]);
  async function respond(id, decision) {
    setBusy(true); setError('');
    try { await api.post(`/project-invitations/${id}/respond`, { decision }); await load(); await onChanged(); } catch (e) { setError(apiErrorMessage(e)); } finally { setBusy(false); }
  }
  return <section className="project-collaboration invitation-inbox" aria-label={txt('项目邀请', 'Project invitations')}><div className="collab-heading"><h2><Users size={17} />{txt('项目邀请', 'Project invitations')} · {items.length}</h2><button className="collab-icon" aria-label={txt('刷新邀请', 'Refresh invitations')} title={txt('刷新邀请', 'Refresh invitations')} disabled={busy} onClick={load}><RefreshCw size={16} /></button></div>
    {error && <p role="alert" className="collab-error">{systemText(error)}</p>}{!items.length && <p className="collab-muted">{txt('暂无待处理邀请', 'No pending invitations')}</p>}
    {items.map(item => <div className="collab-invitation" key={item.id}><div><strong>{item.project_name}</strong><p>{item.inviter} · {item.role === 'admin' ? txt('项目管理员', 'Project administrator') : txt('项目成员', 'Project member')} · {txt('到期', 'Expires')} {new Date(item.expires_at).toLocaleDateString(getLocale())}</p></div><div className="collab-actions"><button className="collab-icon" title={txt('接受邀请', 'Accept invitation')} aria-label={`${txt('接受邀请', 'Accept invitation')} ${item.project_name}`} disabled={busy} onClick={() => respond(item.id, 'accept')}><Check size={17} /></button><button className="collab-icon" title={txt('拒绝邀请', 'Decline invitation')} aria-label={`${txt('拒绝邀请', 'Decline invitation')} ${item.project_name}`} disabled={busy} onClick={() => respond(item.id, 'decline')}><X size={17} /></button></div></div>)}
  </section>;
}

export default function ProjectCollaboration({ project, onChanged, initialTab = 'members' }) {
  const { api, user, txt } = useProjectApi();
  const [data, setData] = useState(null), [tab, setTab] = useState(initialTab), [username, setUsername] = useState(''), [role, setRole] = useState('member');
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const pid = project.id;
  const load = useCallback(async () => { setData((await api.get(`/projects/${pid}/collaboration`)).data); }, [api, pid]);
  useEffect(() => { let cancelled = false; setData(null); setError(''); setTab(initialTab); setUsername(''); api.get(`/projects/${pid}/collaboration`).then(r => { if (!cancelled) setData(r.data); }).catch(e => { if (!cancelled) setError(apiErrorMessage(e)); }); return () => { cancelled = true; }; }, [api, pid]);
  const manager = data?.my_role === 'admin';
  async function act(fn) { if (busy) return; setBusy(true); setError(''); try { await fn(); await onChanged(); try { await load(); } catch (e) { if (e.response?.status !== 404) throw e; } } catch (e) { setError(apiErrorMessage(e)); } finally { setBusy(false); } }
  function remove(member) {
    if (!window.confirm(member.id === user.id ? txt('退出后将失去项目访问权，已贡献内容保留。确认退出？', 'Leave this project? Contributions are retained, but access is revoked.') : txt(`移除 ${member.username}？其已贡献内容将保留。`, `Remove ${member.username}? Contributions are retained.`))) return;
    act(() => api.delete(`/projects/${pid}/members/${member.id}`));
  }
  return <section className="project-collaboration" aria-label={txt('项目协作', 'Project collaboration')}>
    <div className="collab-heading"><h2><Users size={17} />{txt('项目协作', 'Project collaboration')}</h2><span className="collab-muted">{manager ? txt('我的角色：项目管理员', 'My role: project administrator') : txt('我的角色：项目成员', 'My role: project member')}</span><button className="collab-icon" title={txt('刷新协作信息', 'Refresh collaboration')} aria-label={txt('刷新协作信息', 'Refresh collaboration')} disabled={busy} onClick={() => act(async () => {})}><RefreshCw size={16} /></button></div>
    {error && <p role="alert" className="collab-error">{systemText(error)}</p>}
    <div className="collab-tabs" role="tablist" aria-label={txt('项目协作视图', 'Collaboration views')}>{[['members', '成员', 'Members'], ['events', '活动', 'Activity']].map(([key, zh, en]) => <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>{txt(zh, en)}</button>)}</div>
    {!data ? <p className="collab-muted">{txt('正在加载', 'Loading')}</p> : <>
      {tab === 'members' && <>
        {manager && <form className="collab-invite-form" onSubmit={e => { e.preventDefault(); act(async () => { await api.post(`/projects/${pid}/invitations`, { username, role }); setUsername(''); }); }}><label>{txt('已注册用户名', 'Registered username')}<input aria-label={txt('邀请用户名', 'Invite username')} required minLength={3} maxLength={32} value={username} disabled={busy} onChange={e => setUsername(e.target.value)} /></label><label>{txt('项目角色', 'Project role')}<select aria-label={txt('邀请项目角色', 'Invited project role')} value={role} disabled={busy} onChange={e => setRole(e.target.value)}><option value="member">{txt('项目成员', 'Project member')}</option><option value="admin">{txt('项目管理员', 'Project administrator')}</option></select></label><button disabled={busy || !username.trim()} type="submit"><Send size={16} />{txt('邀请', 'Invite')}</button></form>}
        <div className="collab-table"><table><thead><tr><th>{txt('成员', 'Member')}</th><th>{txt('项目角色', 'Project role')}</th><th>{txt('操作', 'Actions')}</th></tr></thead><tbody>{data.members.map(member => <tr key={member.id}><td>{member.username}{!member.is_active && <small> · {txt('账号停用', 'Account disabled')}</small>}{member.is_owner === 1 && <small> · {txt('所有者', 'Owner')}</small>}</td><td>{manager && member.id !== user.id && !member.is_owner ? <select aria-label={`${txt('项目角色', 'Project role')} ${member.username}`} disabled={busy} value={member.role} onChange={e => act(() => api.patch(`/projects/${pid}/members/${member.id}`, { role: e.target.value }))}><option value="member">{txt('项目成员', 'Project member')}</option><option value="admin">{txt('项目管理员', 'Project administrator')}</option></select> : member.role === 'admin' ? txt('项目管理员', 'Project administrator') : txt('项目成员', 'Project member')}</td><td><div className="collab-actions">{data.owner_id === user.id && member.id !== user.id && Boolean(member.is_active) && <button disabled={busy} onClick={() => { if (window.confirm(txt(`将项目所有权转让给 ${member.username}？`, `Transfer project ownership to ${member.username}?`))) act(() => api.post(`/projects/${pid}/transfer`, { user_id: member.id })); }}>{txt('转让所有权', 'Transfer ownership')}</button>}{!member.is_owner && (manager || member.id === user.id) && <button className="collab-icon" title={member.id === user.id ? txt('退出项目', 'Leave project') : txt('移除成员', 'Remove member')} aria-label={`${member.id === user.id ? txt('退出项目', 'Leave project') : txt('移除成员', 'Remove member')} ${member.username}`} disabled={busy} onClick={() => remove(member)}>{member.id === user.id ? <LogOut size={16} /> : <UserMinus size={16} />}</button>}</div></td></tr>)}</tbody></table></div>
        {manager && data.invitations.length > 0 && <div><h3>{txt('待接受邀请', 'Pending invitations')}</h3>{data.invitations.map(item => <div key={item.id} className="collab-invitation"><span>{item.username} · {item.role === 'admin' ? txt('项目管理员', 'Project administrator') : txt('项目成员', 'Project member')} · {new Date(item.expires_at).toLocaleDateString(getLocale())}</span><button className="collab-icon" title={txt('撤销邀请', 'Revoke invitation')} aria-label={`${txt('撤销邀请', 'Revoke invitation')} ${item.username}`} disabled={busy} onClick={() => act(() => api.delete(`/projects/${pid}/invitations/${item.id}`))}><Trash2 size={16} /></button></div>)}</div>}
      </>}
      {tab === 'events' && <ol className="collab-events">{!data.events.length && <li className="collab-muted">{txt('暂无活动', 'No activity')}</li>}{data.events.map(item => <li key={item.id}><time>{new Date(item.created_at).toLocaleString(getLocale())}</time><strong>{item.actor}</strong><span>{txt(actions[item.action] || item.action, item.action)}</span><span>{data.members.find(m => m.id === item.target)?.username || item.target}</span></li>)}</ol>}
    </>}
  </section>;
}
