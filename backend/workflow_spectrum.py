"""Read a completed spectrum version from authoritative, permission-checked storage."""
import json
from fastapi import HTTPException


def freeze_workflow_spectrum(conn, h, workflow_id, version_id, user):
    row = conn.execute('SELECT * FROM ai_workflows WHERE id=? AND user_id=?', (workflow_id, user['id'])).fetchone()
    if row is None:
        raise HTTPException(404, '光谱任务不存在。')
    if row['project_id']:
        h['get_project_row'](conn, row['project_id'], user)
    spectrum, steps = json.loads(row['original_json']), []
    if version_id:
        version = conn.execute('SELECT * FROM ai_plan_versions WHERE id=? AND workflow_id=?', (version_id, row['id'])).fetchone()
        if version is None:
            raise HTTPException(404, '处理版本不属于此光谱。')
        if version['status'] != 'completed':
            raise HTTPException(400, '只能使用已保存的处理结果。')
        trace = json.loads(version['trace_json'])
        if not trace or not trace[-1].get('after'):
            raise HTTPException(400, '处理结果为空。')
        spectrum, steps = trace[-1]['after'], json.loads(version['steps_json'])
    source = dict(spectrum={key: spectrum[key] for key in ('wavenumber', 'intensity')},
                  reference=dict(workflow_id=row['id'], version_id=version_id), steps=steps,
                  metadata=json.loads(row['diagnostics_json']).get('source_check', {}))
    return source, row['source_name'], row['project_id']
