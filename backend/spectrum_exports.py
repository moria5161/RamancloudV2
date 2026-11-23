"""Permission-checked, immutable spectrum data for browser TXT/PNG ZIP exports."""
import json
from typing import List, Optional

from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, Field, root_validator


class SpectrumReference(BaseModel):
    run_id: Optional[str] = None
    workflow_id: Optional[str] = None
    version_id: Optional[str] = None

    @root_validator
    def one_source(cls, values):
        if bool(values.get('run_id')) == bool(values.get('workflow_id')):
            raise ValueError('每条光谱需指定一个结果或任务。')
        if values.get('run_id') and values.get('version_id'):
            raise ValueError('结果记录已确定版本。')
        return values


class SpectrumExportRequest(BaseModel):
    spectra: List[SpectrumReference] = Field(..., min_items=1, max_items=100)
    original: bool = False
    processed: bool = True

    @root_validator
    def has_role(cls, values):
        if not values.get('original') and not values.get('processed'):
            raise ValueError('请选择原始或处理后光谱。')
        return values


def spectrum(value):
    wave, intensity = value.get('wavenumber'), value.get('intensity')
    if isinstance(wave, list) and isinstance(intensity, list) and wave and len(wave) == len(intensity):
        return dict(wavenumber=wave, intensity=intensity)
    return None


def install_spectrum_exports(app, h):
    @app.post('/api/spectra/export-data')
    def export_data(payload: SpectrumExportRequest, response: Response, user=Depends(h['get_current_user'])):
        items, skipped, seen, point_count = [], [], set(), 0
        with h['db_connect']() as conn:
            for ref in payload.spectra:
                key = (ref.run_id, ref.workflow_id, ref.version_id)
                if key in seen:
                    continue
                seen.add(key)
                number, version_id = None, ref.version_id
                if ref.run_id:
                    row = h['get_analysis_run_row'](conn, ref.run_id, user)
                    run = h['row_to_analysis_run'](row)
                    if run['analysis_type'] != 'spectrum':
                        raise HTTPException(400, '此入口仅导出单光谱处理记录。')
                    source_name = run['source_name']
                    raw, final = spectrum(run['input']), spectrum(run['result'])
                    number = run['result'].get('ai_version_number')
                    wid, version_id = run['result'].get('ai_workflow_id'), run['result'].get('ai_version_id')
                    if not number and wid and version_id:
                        versions = conn.execute('SELECT id FROM ai_plan_versions WHERE workflow_id=? ORDER BY created_at,id', (wid,)).fetchall()
                        number = next((i+1 for i, version in enumerate(versions) if version['id'] == version_id), None)
                else:
                    row = conn.execute('''SELECT w.* FROM ai_workflows w JOIN ai_workflow_origins o ON o.workflow_id=w.id
                        WHERE w.id=? AND w.user_id=? AND o.module='preprocessing' ''', (ref.workflow_id,user['id'])).fetchone()
                    if row is None:
                        raise HTTPException(404, '光谱任务不存在。')
                    if row['project_id']:
                        h['get_project_row'](conn, row['project_id'], user)
                    source_name, wid = row['source_name'], row['id']
                    raw, final = spectrum(json.loads(row['original_json'])), None
                    versions = conn.execute('SELECT id,status FROM ai_plan_versions WHERE workflow_id=? ORDER BY created_at,id', (wid,)).fetchall()
                    if version_id:
                        version = next((v for v in versions if v['id'] == version_id), None)
                        if version is None:
                            raise HTTPException(404, '处理版本不存在。')
                    else:
                        version = next((v for v in reversed(versions) if v['status'] == 'completed'), None)
                    if version:
                        version_id = version['id']
                        number = next(i+1 for i, v in enumerate(versions) if v['id'] == version_id)
                        if version['status'] == 'completed' and payload.processed:
                            trace = json.loads(conn.execute('SELECT trace_json FROM ai_plan_versions WHERE id=?', (version_id,)).fetchone()['trace_json'])
                            final = spectrum(trace[-1].get('after', {})) if trace else None
                item = dict(source_name=source_name, run_id=ref.run_id, workflow_id=wid, version_id=version_id, version=number)
                for role, requested, data in [('original',payload.original,raw), ('processed',payload.processed,final)]:
                    if not requested:
                        continue
                    if data is None:
                        skipped.append(dict(source_name=source_name, role=role, reason='无已完成的处理结果' if role == 'processed' else '缺少原始光谱数据'))
                    else:
                        point_count += len(data['wavenumber'])
                        if point_count > 2000000:
                            raise HTTPException(413, '本次数据量较大，请分批导出。')
                        item[role] = data
                if 'original' in item or 'processed' in item:
                    items.append(item)
        # No source, task, history or project state is changed by export.
        response.headers['Cache-Control'] = 'private, no-store'
        return dict(items=items, skipped=skipped)
