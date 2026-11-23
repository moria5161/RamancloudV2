"""Permission checked task evidence and explicitly saved project discussions."""
import json
import uuid
import numpy as np
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from scipy.signal import find_peaks, peak_widths
import ai_workflow as workflow


def peak_profiles(x, y):
    span = max(float(np.ptp(y)), 1e-12)
    delta = np.diff(y)
    noise = float(np.median(np.abs(delta-np.median(delta))) / (0.6745*np.sqrt(2)))
    peaks, props = find_peaks(y, prominence=max(noise*4, span*0.03))
    top = np.argsort(props['prominences'])[-8:][::-1]
    chosen = peaks[top]
    widths = peak_widths(y, chosen, rel_height=0.5)
    axis = np.arange(len(x))
    return [dict(position=float(x[p]), height=float(y[p]), prominence=float(props['prominences'][top[i]]),
                 half_prominence_width=float(abs(np.interp(widths[3][i], axis, x)-np.interp(widths[2][i], axis, x))))
            for i, p in enumerate(chosen)]


def compact_diagnostics(value):
    # Native mapping imports may carry every position's preview in source_check.
    # Only scalar statistics for the selected spectrum belong in model evidence.
    result = {key: item[:200] if isinstance(item, str) else item for key, item in value.items()
              if item is None or isinstance(item, (str, int, float, bool))}
    source = value.get('source_check') or {}
    result['axis_unit'] = str(source.get('axis_unit', '未声明'))[:80]
    result['import_warnings'] = [str(item)[:300] for item in source.get('warnings', [])[:3]]
    return result


def record_evidence(h, run_id, user):
    with h['db_connect']() as conn:
        row = h['get_analysis_run_row'](conn, run_id, user)
    run = h['row_to_analysis_run'](row)
    evidence = dict(run_id=run_id, filename=run['source_name'], title=run['title'], project_id=run['project_id'],
        analysis_type=run['analysis_type'], status='completed', steps=run['steps'],
        sources=[dict(id='plan', label='有访问权限的已完成分析记录、算法与参数')])
    original, after = run['input'], run['result']
    try:
        ox, oy = workflow.validate_spectrum(original['wavenumber'], original.get('intensity', original.get('mean_spectrum')))
        evidence['original'] = compact_diagnostics(workflow.diagnostics(ox, oy))
        evidence['sources'].append(dict(id='input', label='已保存记录中的原始光谱统计'))
    except (ValueError, TypeError, KeyError):
        pass
    try:
        evidence['comparison'] = comparison_evidence(original, after)
        evidence['sources'].append(dict(id='comparison', label='已完成记录的同波段前后数据诊断（程序计算）'))
    except (ValueError, TypeError, KeyError):
        evidence['comparison_note'] = '该记录没有可比较的完整单谱数组；不从预览或缩略图推断数值结论。'
    candidates = after.get('candidates') or after.get('result', {}).get('candidates') or []
    evidence['candidates'] = [{key: item[key] for key in ('rank', 'name', 'formula', 'smiles', 'model_score', 'matching_score')
        if key in item and isinstance(item[key], (str, int, float, bool))} for item in candidates[:5]]
    evidence['result_summary'] = {key: after[key] for key in ('model_name', 'rf_score', 'duration_seconds') if key in after}
    return evidence


def comparison_evidence(original, after):
    x, y = workflow.validate_spectrum(after['wavenumber'], after['intensity'])
    ox, oy = workflow.validate_spectrum(original['wavenumber'], original['intensity'])
    keep = (ox >= x.min()) & (ox <= x.max())
    if np.count_nonzero(keep) < 8 or x.min() < ox.min() or x.max() > ox.max():
        raise ValueError('Cannot compare different physical ranges')
    before, final = workflow.diagnostics(ox[keep], oy[keep]), workflow.diagnostics(x, y)
    order = np.argsort(ox)
    aligned = np.interp(x, ox[order], oy[order])
    indices = np.unique(np.linspace(0, len(x)-1, min(48, len(x))).astype(int))
    return dict(before=before, after=final, before_peaks=peak_profiles(ox[keep], oy[keep]), after_peaks=peak_profiles(x, y),
        rmse_change=float(np.sqrt(np.mean((aligned-y)**2))), max_absolute_change=float(np.max(np.abs(aligned-y))),
        sampled_pairs=[[float(x[i]), float(aligned[i]), float(y[i])] for i in indices],
        note='同波段完整数组统计；峰宽为半突出度宽度，不等同于拟合半高宽。变化量不是准确率，噪声比是差分MAD/强度跨度；自动检峰受阈值影响，不能单独证明降噪或峰保留。')


def task_evidence(h, task_id, version_id, user):
    hooks = h['_qa_workflow']
    task = hooks['detail'](task_id, user)
    result = dict(task_id=task_id, filename=task['source_name'], project_id=task['project_id'],
                  original=compact_diagnostics(task['diagnostics']), sources=[dict(id='input', label='服务器保存的原始光谱统计')])
    if not version_id:
        version_id = task['versions'][-1]['id'] if task['versions'] else None
    if version_id:
        with h['db_connect']() as conn:
            version = hooks['decode_version'](hooks['version_row'](conn, task_id, version_id))
        result.update(version_id=version_id, status=version['status'], goal=version['goal'], steps=version['steps'])
        result['sources'].append(dict(id='plan', label='所选版本的实际算法、参数与执行状态'))
        records = version['trace'] or version['preview']
        result['warnings'] = list(dict.fromkeys(w for r in records for w in r.get('warnings', [])))
        if records:
            result['comparison'] = comparison_evidence(task['original'], records[-1]['after'])
            result['comparison']['note'] += '失败、运行中或预览版本只代表已计算的步骤。'
            result['sources'].append(dict(id='comparison', label='同波段完整数据的前后诊断与变化量（程序计算）'))
    return result


class SaveNote(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    content: str = Field(..., min_length=1, max_length=24000)
    task_id: str = Field('', max_length=64)
    version_id: str = Field('', max_length=64)
    expected_status: str = Field('', max_length=24)


def install_context(app, h):
    db, auth = h['db_connect'], h['get_current_user']
    with db() as conn:
        conn.execute(f'''CREATE TABLE IF NOT EXISTS qa_project_notes (
            id {h['ID_SQL']} PRIMARY KEY, project_id {h['ID_SQL']} NOT NULL,
            user_id {h['ID_SQL']} NOT NULL, title {h['NAME_SQL']} NOT NULL,
            content {h['JSON_SQL']} NOT NULL, evidence_json {h['JSON_SQL']} NOT NULL,
            created_at {h['DATE_SQL']} NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ){h['TABLE_OPTIONS']}''')

    @app.get('/api/qa-assistant/context/{task_id}')
    def context(task_id: str, version_id: str = '', user=Depends(auth)):
        return task_evidence(h, task_id, version_id, user)

    @app.get('/api/qa-assistant/records/{run_id}/context')
    def saved_context(run_id: str, user=Depends(auth)):
        return record_evidence(h, run_id, user)

    @app.post('/api/qa-assistant/projects/{project_id}/notes')
    def save(project_id: str, payload: SaveNote, user=Depends(auth)):
        if not payload.title.strip() or not payload.content.strip():
            raise HTTPException(400, '标题和内容不能为空。')
        with db() as conn:
            h['get_project_row'](conn, project_id, user)
        evidence = task_evidence(h, payload.task_id, payload.version_id, user) if payload.task_id else {}
        if evidence.get('status') in ('queued', 'running', 'previewing') or (payload.expected_status and evidence.get('status') != payload.expected_status):
            raise HTTPException(409, '版本状态已变化或仍在运行，请在处理完成后重新提问再保存依据。')
        if evidence and evidence.get('project_id') != project_id:
            raise HTTPException(400, '任务必须属于所选项目，防止把私人任务分享给其他项目。')
        nid = uuid.uuid4().hex
        with db() as conn:
            h['get_project_row'](conn, project_id, user)
            conn.execute('INSERT INTO qa_project_notes (id,project_id,user_id,title,content,evidence_json,created_at) VALUES (?,?,?,?,?,?,?)',
                (nid, project_id, user['id'], payload.title.strip(), payload.content,
                 json.dumps(evidence, ensure_ascii=False), h['iso_now']()))
        return dict(id=nid)

    @app.get('/api/qa-assistant/projects/{project_id}/notes')
    def notes(project_id: str, offset: int = Query(0, ge=0), user=Depends(auth)):
        with db() as conn:
            h['get_project_row'](conn, project_id, user)
            rows = conn.execute('SELECT id,title,content,user_id,created_at FROM qa_project_notes WHERE project_id=? ORDER BY created_at DESC,id DESC LIMIT 20 OFFSET ?', (project_id, offset)).fetchall()
        return [dict(row) for row in rows]

    @app.get('/api/qa-assistant/projects/{project_id}/notes/{note_id}')
    def note(project_id: str, note_id: str, user=Depends(auth)):
        with db() as conn:
            h['get_project_row'](conn, project_id, user)
            row = conn.execute('SELECT * FROM qa_project_notes WHERE id=? AND project_id=?', (note_id, project_id)).fetchone()
        if row is None:
            raise HTTPException(404, '问答记录不存在。')
        return dict(row)

    @app.delete('/api/qa-assistant/projects/{project_id}/notes/{note_id}')
    def delete(project_id: str, note_id: str, user=Depends(auth)):
        with db() as conn:
            project = h['get_project_row'](conn, project_id, user)
            row = conn.execute('SELECT user_id FROM qa_project_notes WHERE id=? AND project_id=?', (note_id, project_id)).fetchone()
            if row is None:
                raise HTTPException(404, '问答记录不存在。')
            if row['user_id'] != user['id'] and project['my_role'] != 'admin':
                raise HTTPException(403, '仅作者或项目管理员可删除。')
            conn.execute('DELETE FROM qa_project_notes WHERE id=?', (note_id,))
        return dict(deleted=True)
