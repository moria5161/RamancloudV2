"""Persistent, private user feedback and a platform-administrator inbox."""
import uuid
from datetime import timedelta
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Response
from pydantic import BaseModel, constr


CATEGORY = constr(regex=r'^(bug|suggestion|data|tutorial|other)$')
STATUS = constr(regex=r'^(new|in_progress|resolved)$')
PAGES = {'/', '/tutorial', '/ai-analysis', '/hyperspectral', '/spectral-unmixing',
         '/library-matching', '/structure-generation', '/projects', '/analysis-history',
         '/extra-tools', '/account', '/contributors', '/feedback'}
MAX_PER_WINDOW = 5
WINDOW = timedelta(minutes=10)


class FeedbackCreate(BaseModel):
    request_id: UUID
    category: CATEGORY = 'bug'
    title: constr(strip_whitespace=True, min_length=3, max_length=120)
    body: constr(strip_whitespace=True, min_length=10, max_length=5000)
    page_path: constr(strip_whitespace=True, max_length=80) = '/tutorial'

    class Config:
        extra = 'forbid'


class FeedbackUpdate(BaseModel):
    status: STATUS
    reply: Optional[constr(strip_whitespace=True, max_length=3000)] = None
    expected_updated_at: constr(min_length=1, max_length=40)

    class Config:
        extra = 'forbid'


def check_text(*values):
    if any(ord(character) < 32 and character not in '\n\r\t' for value in values for character in value):
        raise HTTPException(400, '反馈文字不能包含控制字符。')


def install_feedback(app, h):
    db, now, auth, admin = h['db_connect'], h['iso_now'], h['get_current_user'], h['require_admin']
    with db() as conn:
        conn.execute(f'''CREATE TABLE IF NOT EXISTS user_feedback (
            id {h['ID_SQL']} PRIMARY KEY, user_id {h['ID_SQL']} NOT NULL,
            request_id {h['ID_SQL']} NOT NULL, category {h['SHORT_SQL']} NOT NULL,
            title {h['NAME_SQL']} NOT NULL, body TEXT NOT NULL,
            page_path {h['NAME_SQL']} NOT NULL, status {h['SHORT_SQL']} NOT NULL,
            reply TEXT NOT NULL, replied_by {h['ID_SQL']}, replied_at {h['DATE_SQL']},
            created_at {h['DATE_SQL']} NOT NULL, updated_at {h['DATE_SQL']} NOT NULL,
            UNIQUE(user_id, request_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(replied_by) REFERENCES users(id) ON DELETE SET NULL
        ){h['TABLE_OPTIONS']}''')
        h['create_index'](conn, 'idx_feedback_owner_created', 'user_feedback', 'user_id,created_at')
        h['create_index'](conn, 'idx_feedback_status_created', 'user_feedback', 'status,created_at')

    selection = '''SELECT f.*, u.username, u.display_name FROM user_feedback f
                   JOIN users u ON u.id=f.user_id'''

    def serialize(row, detail=True):
        result = {key: row[key] for key in ('id', 'user_id', 'category', 'title', 'page_path', 'status',
                  'replied_at', 'created_at', 'updated_at', 'username', 'display_name')}
        result['display_name'] = result['display_name'] or result['username']
        if detail:
            result.update(body=row['body'], reply=row['reply'])
        else:
            result.update(preview=row['body'][:180], has_reply=bool(row['reply']))
        return result

    def readable(conn, fid, user):
        sql, params = selection + ' WHERE f.id=?', [fid]
        if user['role'] != 'admin':
            sql += ' AND f.user_id=?'
            params.append(user['id'])
        row = conn.execute(sql, tuple(params)).fetchone()
        if row is None:
            raise HTTPException(404, '反馈不存在。')
        return row

    @app.post('/api/feedback')
    def submit(payload: FeedbackCreate, response: Response, user=Depends(auth)):
        if user['role'] == 'admin':
            raise HTTPException(403, '系统管理员负责处理用户反馈，不能提交新反馈。')
        if payload.page_path not in PAGES:
            raise HTTPException(400, '反馈来源必须是站内页面路径，不包含查询参数。')
        check_text(payload.title, payload.body)
        rid = str(payload.request_id)
        fields = (payload.category, payload.title, payload.body, payload.page_path)
        with db() as conn:
            # Serialize this user's quota and idempotency check across concurrent requests.
            if h['DB_ENGINE'] == 'mysql':
                conn.execute('SELECT id FROM users WHERE id=? FOR UPDATE', (user['id'],)).fetchone()
            else:
                conn.execute('BEGIN IMMEDIATE')
            previous = conn.execute('SELECT * FROM user_feedback WHERE user_id=? AND request_id=?', (user['id'], rid)).fetchone()
            if previous:
                if tuple(previous[key] for key in ('category', 'title', 'body', 'page_path')) != fields:
                    raise HTTPException(409, '该提交编号已用于另一份反馈，请重新提交。')
                return serialize(readable(conn, previous['id'], user))
            since = (h['utc_now']() - WINDOW).isoformat()
            count = conn.execute('SELECT COUNT(*) AS count FROM user_feedback WHERE user_id=? AND created_at>=?', (user['id'], since)).fetchone()['count']
            if int(count) >= MAX_PER_WINDOW:
                raise HTTPException(429, '提交较频繁，每 10 分钟最多 5 条反馈，请稍后再试。', headers={'Retry-After': '600'})
            fid, stamp = uuid.uuid4().hex, now()
            conn.execute('''INSERT INTO user_feedback
                (id,user_id,request_id,category,title,body,page_path,status,reply,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (fid, user['id'], rid, *fields, 'new', '', stamp, stamp))
            result = serialize(readable(conn, fid, user))
        response.status_code = 201
        return result

    @app.get('/api/feedback')
    def inbox(scope: constr(regex=r'^(mine|all)$') = 'mine', status: Optional[STATUS] = None,
              category: Optional[CATEGORY] = None, page: int = Query(1, ge=1, le=100000),
              page_size: int = Query(20, ge=1, le=50), user=Depends(auth)):
        if scope == 'all' and user['role'] != 'admin':
            raise HTTPException(403, '仅系统管理员可查看全部反馈。')
        clauses, params = [], []
        if scope == 'mine':
            clauses.append('f.user_id=?')
            params.append(user['id'])
        owner_where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with db() as conn:
            counts = {value: 0 for value in ('new', 'in_progress', 'resolved')}
            for row in conn.execute('SELECT f.status,COUNT(*) AS count FROM user_feedback f' + owner_where + ' GROUP BY f.status', tuple(params)).fetchall():
                counts[row['status']] = int(row['count'])
            for key, value in [('status', status), ('category', category)]:
                if value:
                    clauses.append(f'f.{key}=?')
                    params.append(value)
            where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
            total = conn.execute('SELECT COUNT(*) AS count FROM user_feedback f' + where, tuple(params)).fetchone()['count']
            rows = conn.execute(selection + where + ' ORDER BY f.created_at DESC,f.id DESC LIMIT ? OFFSET ?',
                                (*params, page_size, (page - 1) * page_size)).fetchall()
        return dict(items=[serialize(row, detail=False) for row in rows], total=int(total), counts=counts,
                    page=page, page_size=page_size)

    @app.get('/api/feedback/{fid}')
    def detail(fid: str, user=Depends(auth)):
        with db() as conn:
            return serialize(readable(conn, fid, user))

    @app.patch('/api/feedback/{fid}')
    def update(fid: str, payload: FeedbackUpdate, user=Depends(admin)):
        if payload.reply is not None:
            check_text(payload.reply)
        with db() as conn:
            row = readable(conn, fid, user)
            reply = row['reply'] if payload.reply is None else payload.reply
            stamp = now()
            changed_reply = reply != row['reply']
            changed = conn.execute('''UPDATE user_feedback SET status=?,reply=?,replied_by=?,replied_at=?,updated_at=?
                WHERE id=? AND updated_at=?''',
                (payload.status, reply, user['id'] if changed_reply else row['replied_by'],
                 stamp if changed_reply else row['replied_at'], stamp, fid, payload.expected_updated_at))
            if changed.rowcount != 1:
                raise HTTPException(409, '反馈已被其他管理员更新，请刷新后再处理。')
            return serialize(readable(conn, fid, user))
