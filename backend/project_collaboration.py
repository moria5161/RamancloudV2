"""Project-scoped collaboration, independent of platform administrator privileges."""
import uuid
from datetime import timedelta

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field


def project_access(conn, project_id, user):
    row = conn.execute("""SELECT p.*, u.username AS owner_username,
        CASE WHEN p.owner_id = ? THEN 'admin' ELSE m.role END AS my_role
        FROM projects p JOIN users u ON u.id = p.owner_id
        LEFT JOIN project_members m ON m.project_id = p.id AND m.user_id = ?
        WHERE p.id = ? AND (p.owner_id = ? OR m.user_id IS NOT NULL)""",
        (user['id'], user['id'], project_id, user['id'])).fetchone()
    if row is None:
        raise HTTPException(404, '项目不存在或你已无权访问。')
    return row


def project_admin(conn, project_id, user):
    row = project_access(conn, project_id, user)
    if row['my_role'] != 'admin':
        raise HTTPException(403, '仅项目管理员可执行此操作。')
    return row


def project_list_query(user, include_counts=True):
    counts = """, (SELECT COUNT(*) FROM data_assets d WHERE d.project_id = projects.id) AS dataset_count,
        (SELECT COUNT(*) FROM data_assets d WHERE d.project_id = projects.id AND d.data_kind = 'raw') AS raw_count,
        (SELECT COUNT(*) FROM data_assets d WHERE d.project_id = projects.id AND d.data_kind = 'processed') AS processed_count""" if include_counts else ''
    return (f"""SELECT projects.*, users.username AS owner_username,
        CASE WHEN projects.owner_id = ? THEN 'admin' ELSE m.role END AS my_role {counts}
        FROM projects JOIN users ON users.id = projects.owner_id
        LEFT JOIN project_members m ON m.project_id = projects.id AND m.user_id = ?
        WHERE projects.owner_id = ? OR m.user_id IS NOT NULL ORDER BY projects.updated_at DESC""",
        (user['id'], user['id'], user['id']))


def event(conn, project_id, user, action, target=''):
    conn.execute('INSERT INTO project_events (id,project_id,actor,action,target,created_at) VALUES (?,?,?,?,?,?)',
                 (uuid.uuid4().hex, project_id, user['username'], action, target, _now()))


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


class Invite(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    role: str = Field('member', regex='^(admin|member)$')


class Respond(BaseModel):
    decision: str = Field(..., regex='^(accept|decline)$')


class MemberRole(BaseModel):
    role: str = Field(..., regex='^(admin|member)$')


class Transfer(BaseModel):
    user_id: str


def install_collaboration(app, h):
    db, auth, now = h['db_connect'], h['get_current_user'], h['iso_now']
    with db() as conn:
        conn.execute(f"""CREATE TABLE IF NOT EXISTS project_invitations (
            id {h['ID_SQL']} PRIMARY KEY, project_id {h['ID_SQL']} NOT NULL,
            user_id {h['ID_SQL']} NOT NULL, invited_by {h['ID_SQL']} NOT NULL,
            role {h['SHORT_SQL']} NOT NULL, status {h['SHORT_SQL']} NOT NULL,
            created_at {h['DATE_SQL']} NOT NULL, expires_at {h['DATE_SQL']} NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ){h['TABLE_OPTIONS']}""")
        conn.execute(f"""CREATE TABLE IF NOT EXISTS project_events (
            id {h['ID_SQL']} PRIMARY KEY, project_id {h['ID_SQL']} NOT NULL,
            actor {h['USERNAME_SQL']} NOT NULL, action {h['SHORT_SQL']} NOT NULL,
            target {h['NAME_SQL']} NOT NULL, created_at {h['DATE_SQL']} NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        ){h['TABLE_OPTIONS']}""")
        conn.execute(f"""CREATE TABLE IF NOT EXISTS project_result_shares (
            run_id {h['ID_SQL']} PRIMARY KEY, project_id {h['ID_SQL']} NOT NULL,
            shared_by {h['ID_SQL']} NOT NULL, shared_at {h['DATE_SQL']} NOT NULL,
            FOREIGN KEY(run_id) REFERENCES analysis_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        ){h['TABLE_OPTIONS']}""")
        for table, name, columns in [('project_invitations', 'idx_invite_recipient', 'user_id,status'),
                                     ('project_events', 'idx_event_project', 'project_id,created_at'),
                                     ('project_result_shares', 'idx_share_project', 'project_id')]:
            h['create_index'](conn, name, table, columns)
        conn.execute("UPDATE users SET role = 'user' WHERE role = 'member'")

    def lock(conn, pid, user, owner=False):
        project_admin(conn, pid, user)
        conn.execute('UPDATE projects SET updated_at = updated_at WHERE id = ?', (pid,))
        row = project_admin(conn, pid, user)
        if owner and row['owner_id'] != user['id']:
            raise HTTPException(403, '仅项目所有者可执行此操作。')
        return row

    def members(conn, pid):
        return conn.execute("""SELECT u.id,u.username,u.display_name,u.is_active,
            CASE WHEN p.owner_id = u.id THEN 'admin' ELSE m.role END AS role,
            CASE WHEN p.owner_id = u.id THEN 1 ELSE 0 END AS is_owner
            FROM users u JOIN projects p ON p.id = ?
            LEFT JOIN project_members m ON m.project_id = p.id AND m.user_id = u.id
            WHERE u.id = p.owner_id OR m.user_id IS NOT NULL ORDER BY u.username""", (pid,)).fetchall()

    @app.get('/api/project-invitations')
    def inbox(user=Depends(auth)):
        with db() as conn:
            rows = conn.execute("""SELECT i.*,p.name AS project_name,u.username AS inviter
                FROM project_invitations i JOIN projects p ON p.id=i.project_id
                JOIN users u ON u.id=i.invited_by
                WHERE i.user_id=? AND i.status='pending' AND i.expires_at > ? ORDER BY i.created_at DESC""",
                (user['id'], now())).fetchall()
        return dict(invitations=[dict(row) for row in rows])

    @app.get('/api/projects/{pid}/collaboration')
    def overview(pid: str, user=Depends(auth)):
        with db() as conn:
            row = project_access(conn, pid, user)
            pending = conn.execute("""SELECT i.id,i.role,i.expires_at,u.username FROM project_invitations i
                JOIN users u ON u.id=i.user_id WHERE i.project_id=? AND i.status='pending' AND i.expires_at > ?""",
                (pid, now())).fetchall() if row['my_role'] == 'admin' else []
            events = conn.execute('SELECT * FROM project_events WHERE project_id=? ORDER BY created_at DESC LIMIT 50', (pid,)).fetchall()
            shares = conn.execute("""SELECT r.id,r.title,r.analysis_type,r.source_name,u.username,s.shared_at
                FROM project_result_shares s JOIN analysis_runs r ON r.id=s.run_id
                JOIN users u ON u.id=r.user_id WHERE s.project_id=? ORDER BY s.shared_at DESC""", (pid,)).fetchall()
            return dict(my_role=row['my_role'], owner_id=row['owner_id'], members=[dict(m) for m in members(conn, pid)],
                        invitations=[dict(i) for i in pending], results=[dict(s) for s in shares], events=[dict(e) for e in events])

    @app.post('/api/projects/{pid}/invitations')
    def invite(pid: str, payload: Invite, user=Depends(auth)):
        with db() as conn:
            p = lock(conn, pid, user)
            target = conn.execute('SELECT id FROM users WHERE username=? AND is_active=1', (h['normalize_username'](payload.username),)).fetchone()
            if not target:
                raise HTTPException(404, '未找到可邀请的已注册用户。')
            uid = target['id']
            if uid == p['owner_id'] or conn.execute('SELECT user_id FROM project_members WHERE project_id=? AND user_id=?', (pid, uid)).fetchone():
                raise HTTPException(409, '该用户已经是项目成员。')
            if conn.execute("SELECT id FROM project_invitations WHERE project_id=? AND user_id=? AND status='pending' AND expires_at > ?", (pid, uid, now())).fetchone():
                raise HTTPException(409, '已有待接受邀请，请先撤销或等待对方处理。')
            iid = uuid.uuid4().hex
            expires = (h['utc_now']() + timedelta(days=7)).isoformat()
            conn.execute('INSERT INTO project_invitations (id,project_id,user_id,invited_by,role,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?,?)',
                         (iid, pid, uid, user['id'], payload.role, 'pending', now(), expires))
            event(conn, pid, user, 'invite', payload.username)
        return dict(id=iid, expires_at=expires)

    @app.delete('/api/projects/{pid}/invitations/{iid}')
    def revoke(pid: str, iid: str, user=Depends(auth)):
        with db() as conn:
            lock(conn, pid, user)
            changed = conn.execute("UPDATE project_invitations SET status='revoked' WHERE id=? AND project_id=? AND status='pending'", (iid, pid))
            if not changed.rowcount:
                raise HTTPException(409, '邀请不存在或已处理。')
            event(conn, pid, user, 'revoke_invitation', iid)
        return dict(ok=True)

    @app.post('/api/project-invitations/{iid}/respond')
    def respond(iid: str, payload: Respond, user=Depends(auth)):
        with db() as conn:
            invitation = conn.execute('SELECT * FROM project_invitations WHERE id=? AND user_id=?', (iid, user['id'])).fetchone()
            if not invitation:
                raise HTTPException(404, '邀请不存在。')
            pid = invitation['project_id']
            conn.execute('UPDATE projects SET updated_at=updated_at WHERE id=?', (pid,))
            changed = conn.execute("UPDATE project_invitations SET status=? WHERE id=? AND user_id=? AND status='pending' AND expires_at > ?",
                                   ('accepted' if payload.decision == 'accept' else 'declined', iid, user['id'], now()))
            if not changed.rowcount:
                raise HTTPException(409, '邀请已过期、撤销或处理。')
            if payload.decision == 'accept':
                try:
                    project_admin(conn, pid, {'id': invitation['invited_by']})
                except HTTPException as exc:
                    raise HTTPException(409, '邀请发起人已无管理权限，请重新邀请。') from exc
                if not conn.execute('SELECT id FROM users WHERE id=? AND is_active=1', (invitation['invited_by'],)).fetchone():
                    raise HTTPException(409, '邀请发起人账号已停用，请重新邀请。')
                if conn.execute('SELECT user_id FROM project_members WHERE project_id=? AND user_id=?', (pid, user['id'])).fetchone():
                    raise HTTPException(409, '已加入该项目。')
                conn.execute('INSERT INTO project_members (project_id,user_id,role,created_at) VALUES (?,?,?,?)', (pid, user['id'], invitation['role'], now()))
            event(conn, pid, user, payload.decision + '_invitation', iid)
        return dict(ok=True)

    @app.patch('/api/projects/{pid}/members/{uid}')
    def change_role(pid: str, uid: str, payload: MemberRole, user=Depends(auth)):
        with db() as conn:
            p = lock(conn, pid, user)
            if uid == p['owner_id']:
                raise HTTPException(409, '所有者始终是项目管理员，请先转让所有权。')
            if uid == user['id']:
                raise HTTPException(409, '不能变更自己的项目角色。')
            target = conn.execute('SELECT user_id FROM project_members WHERE project_id=? AND user_id=?', (pid, uid)).fetchone()
            if not target:
                raise HTTPException(404, '成员不存在。')
            conn.execute('UPDATE project_members SET role=? WHERE project_id=? AND user_id=?', (payload.role, pid, uid))
            if payload.role == 'member':
                conn.execute("UPDATE project_invitations SET status='revoked' WHERE project_id=? AND invited_by=? AND status='pending'", (pid, uid))
            event(conn, pid, user, 'change_role', uid + ':' + payload.role)
        return dict(ok=True)

    @app.delete('/api/projects/{pid}/members/{uid}')
    def remove_member(pid: str, uid: str, user=Depends(auth)):
        with db() as conn:
            if uid == user['id']:
                project_access(conn, pid, user)
                conn.execute('UPDATE projects SET updated_at=updated_at WHERE id=?', (pid,))
                p = project_access(conn, pid, user)
            else:
                p = lock(conn, pid, user)
            if uid == p['owner_id']:
                raise HTTPException(409, '所有者须先转让项目，不能直接退出或被移除。')
            if not conn.execute('DELETE FROM project_members WHERE project_id=? AND user_id=?', (pid, uid)).rowcount:
                raise HTTPException(404, '成员不存在。')
            conn.execute("UPDATE project_invitations SET status='revoked' WHERE project_id=? AND invited_by=? AND status='pending'", (pid, uid))
            event(conn, pid, user, 'leave' if uid == user['id'] else 'remove_member', uid)
        return dict(ok=True)

    @app.post('/api/projects/{pid}/transfer')
    def transfer(pid: str, payload: Transfer, user=Depends(auth)):
        with db() as conn:
            lock(conn, pid, user, owner=True)
            uid = payload.user_id
            if uid == user['id'] or not conn.execute('SELECT m.user_id FROM project_members m JOIN users u ON u.id=m.user_id WHERE m.project_id=? AND m.user_id=? AND u.is_active=1', (pid, uid)).fetchone():
                raise HTTPException(400, '请选择另一位有效项目成员。')
            conn.execute('UPDATE project_members SET role=? WHERE project_id=? AND user_id=?', ('admin', pid, uid))
            if not conn.execute('SELECT user_id FROM project_members WHERE project_id=? AND user_id=?', (pid, user['id'])).fetchone():
                conn.execute('INSERT INTO project_members (project_id,user_id,role,created_at) VALUES (?,?,?,?)', (pid, user['id'], 'admin', now()))
            else:
                conn.execute('UPDATE project_members SET role=? WHERE project_id=? AND user_id=?', ('admin', pid, user['id']))
            conn.execute('UPDATE projects SET owner_id=?,updated_at=? WHERE id=?', (uid, now(), pid))
            event(conn, pid, user, 'transfer', uid)
        return dict(ok=True)

    @app.post('/api/analysis-runs/{rid}/publish')
    def publish(rid: str, user=Depends(auth)):
        with db() as conn:
            row = h['get_analysis_run_row'](conn, rid, user)
            if row['user_id'] != user['id'] or not row['project_id']:
                raise HTTPException(403, '仅作者可发布本项目的已保存结果。')
            pid = row['project_id']
            project_access(conn, pid, user)
            conn.execute('UPDATE projects SET updated_at=updated_at WHERE id=?', (pid,))
            project_access(conn, pid, user)
            if not conn.execute('SELECT run_id FROM project_result_shares WHERE run_id=?', (rid,)).fetchone():
                conn.execute('INSERT INTO project_result_shares (run_id,project_id,shared_by,shared_at) VALUES (?,?,?,?)', (rid, pid, user['id'], now()))
                event(conn, pid, user, 'publish_result', rid)
        return dict(ok=True)

    @app.delete('/api/analysis-runs/{rid}/publish')
    def unpublish(rid: str, user=Depends(auth)):
        with db() as conn:
            row = h['get_analysis_run_row'](conn, rid, user)
            pid = row['project_id']
            p = project_access(conn, pid, user)
            conn.execute('UPDATE projects SET updated_at=updated_at WHERE id=?', (pid,))
            p = project_access(conn, pid, user)
            if row['user_id'] != user['id'] and p['my_role'] != 'admin':
                raise HTTPException(403, '仅作者或项目管理员可撤下共享结果。')
            conn.execute('DELETE FROM project_result_shares WHERE run_id=?', (rid,))
            event(conn, pid, user, 'unpublish_result', rid)
        return dict(ok=True)
