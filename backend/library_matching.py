"""Library classifier jobs, frozen inputs, model processing and reference comparison."""
import csv
import io
import json
import logging
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from peaknet_package import catalog, configuration, prepare_source
from structure_runtime import LocalRuntime
from module_records import ModuleRecords

LOG = logging.getLogger(__name__)
RUNTIME = LocalRuntime(service='ramancloud-peaknet', script='services/peaknet/server.py', log_name='peaknet-worker.log')
RUNTIME_LOCK = threading.Lock()


class MatchRequest(BaseModel):
    source_id: Optional[str] = Field(None, max_length=64)
    workflow_id: Optional[str] = Field(None, max_length=64)
    version_id: Optional[str] = Field(None, max_length=64)
    reuse_job_id: Optional[str] = Field(None, max_length=64)
    reference_id: Optional[int] = Field(None, ge=0, lt=2805)
    unit_confirmed: bool = False
    top_k: int = Field(3, ge=1, le=10)
    preprocessing_mode: str = Field('auto', regex='^(auto|prepared)$')


def infer(profile, paths, payload):
    with RUNTIME_LOCK:
        return RUNTIME.infer(profile, paths, payload)


def install_library_matching(app, h):
    db, now, auth = h['db_connect'], h['iso_now'], h['get_current_user']
    encode = lambda value: json.dumps(value, ensure_ascii=False, allow_nan=False)
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='peaknet')
    gate = threading.Lock()
    with db() as conn:
        conn.execute(f"""CREATE TABLE IF NOT EXISTS library_match_jobs (
            id {h['ID_SQL']} PRIMARY KEY, user_id {h['ID_SQL']} NOT NULL, project_id {h['ID_SQL']},
            source_name {h['NAME_SQL']} NOT NULL, status {h['SHORT_SQL']} NOT NULL,
            input_json {h['JSON_SQL']} NOT NULL, profile_json {h['JSON_SQL']} NOT NULL,
            settings_json {h['JSON_SQL']} NOT NULL, result_json {h['JSON_SQL']} NOT NULL,
            error {h['JSON_SQL']} NOT NULL, analysis_run_id {h['ID_SQL']},
            created_at {h['DATE_SQL']} NOT NULL, updated_at {h['DATE_SQL']} NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) {h['TABLE_OPTIONS']}""")
        h['create_index'](conn, 'idx_library_match_user', 'library_match_jobs', 'user_id')

    @app.on_event('startup')
    def recover():
        with db() as conn:
            conn.execute("UPDATE library_match_jobs SET status='failed',error=?,updated_at=? WHERE status IN ('queued','running')",
                         ('服务重启，匹配中断。请重新运行。', now()))

    @app.on_event('shutdown')
    def shutdown():
        RUNTIME.close()
        pool.shutdown(wait=False, **({'cancel_futures': True} if sys.version_info >= (3, 9) else {}))

    def job_row(conn, job_id, user):
        row = conn.execute('SELECT * FROM library_match_jobs WHERE id=? AND user_id=?', (job_id, user['id'])).fetchone()
        if row is None:
            raise HTTPException(404, '匹配任务不存在。')
        if row['project_id']:
            h['get_project_row'](conn, row['project_id'], user)
        return row

    def decode(row, detail=True):
        value = {key: row[key] for key in ('id', 'source_name', 'status', 'error', 'analysis_run_id', 'created_at', 'updated_at')}
        value.update(profile=json.loads(row['profile_json']), settings=json.loads(row['settings_json']))
        if detail:
            value.update(input=json.loads(row['input_json']), result=json.loads(row['result_json']))
        return value

    records = ModuleRecords(app, h, 'library-matching', 'library_match', job_row, decode)

    def model_config():
        profile, paths, ready = configuration()
        if not ready:
            raise HTTPException(503, '库匹配模型未安装，请运行 scripts/setup_peaknet.py 后重启后端。')
        return profile, paths

    @app.get('/api/library-matching/config')
    def config(user=Depends(auth)):
        profile, _, ready = configuration()
        labels = catalog() if ready else {}
        example = next((int(key) for key, value in labels.items() if value == '乙醇'), None)
        return dict(profile=profile, ready=ready, example_class_id=example,
                    message='' if ready else '请按 LIBRARY_MATCHING.md 安装库匹配算法包。')

    @app.get('/api/library-matching/catalog')
    def find_materials(q: str = '', user=Depends(auth)):
        labels = catalog()
        needle = q.strip().lower()[:120]
        matches = [dict(class_id=int(key), name=name) for key, name in labels.items() if needle in name.lower() or needle == key]
        return dict(total=len(labels), matched=len(matches), items=matches[:30])

    @app.get('/api/library-matching/references/{class_id}')
    def reference(class_id: int, user=Depends(auth)):
        profile, paths = model_config()
        if not 0 <= class_id < profile['classes']:
            raise HTTPException(404, '当前库中没有此物质。')
        try:
            return infer(profile, paths, dict(action='reference', class_id=class_id))
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc

    def validated(payload, user):
        if not payload.unit_confirmed:
            raise HTTPException(400, '请先确认横轴为拉曼位移 cm⁻¹。')
        profile, paths = model_config()
        if payload.reuse_job_id:
            with db() as conn:
                old = job_row(conn, payload.reuse_job_id, user)
                source, name, project = json.loads(old['input_json'])['source'], old['source_name'], old['project_id']
        elif payload.workflow_id or payload.source_id:
            with db() as conn:
                source, name, project = records.input(conn, payload, user)
        elif payload.reference_id is not None:
            ref = reference(payload.reference_id, user)
            source = dict(spectrum={key: ref[key] for key in ('wavenumber', 'intensity')},
                          reference=dict(reference_id=payload.reference_id, library_id=profile['library_id']),
                          steps=[], metadata=dict(kind='library_cache', source=ref['source']))
            name, project = ref['name'] + ' · 库内验证输入', None
        else:
            raise HTTPException(400, '请先选择光谱。')
        try:
            cropped = prepare_source(source['spectrum'], profile)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return profile, paths, source, name, project, cropped

    @app.post('/api/library-matching/validate')
    def validate(payload: MatchRequest, user=Depends(auth)):
        profile, _, source, _, _, cropped = validated(payload, user)
        has_baseline = any(step.get('type') == 'baseline' and step.get('enabled', True) for step in source['steps'])
        warnings = list(cropped['warnings'])
        if has_baseline and payload.preprocessing_mode == 'auto':
            warnings.append('此版本已经过基线校正，再次运行 AirNet 可能改变峰形；可改为使用当前处理结果。')
        return dict(profile=profile, cropped=cropped, warnings=warnings,
                    preprocessing_mode=payload.preprocessing_mode, has_saved_baseline=has_baseline)

    def run(job_id, user, paths):
        try:
            with db() as conn:
                row = job_row(conn, job_id, user)
                conn.execute("UPDATE library_match_jobs SET status='running',updated_at=? WHERE id=?", (now(), job_id))
            value = decode(row)
            output = infer(value['profile'], paths, dict(spectrum=value['input']['cropped'], top_k=value['settings']['top_k'],
                                                        preprocessing_mode=value['settings']['preprocessing_mode']))
            output['warnings'] = value['input']['cropped']['warnings']
            with db() as conn:
                job_row(conn, job_id, user)
            summary = dict(output,
                           job_id=job_id, profile=value['profile'], score_type=output['score_type'],
                           preprocessing_mode=output['preprocessing_mode'], inference_performed=True,
                           duration_seconds=output['duration_seconds'])
            history = h['save_analysis_run'](current_user=user, analysis_type='library_matching', source_name=row['source_name'],
                                            steps=[dict(type='library_matching', method='peaknet', params=value['settings'])],
                                            input_payload=value['input'], result_payload=summary,
                                            history=[dict(profile=value['profile'], duration_seconds=output['duration_seconds'])],
                                            title=row['source_name'] + ' · 库匹配', project_id=row['project_id'], result_filename='library_match.json')
            with db() as conn:
                conn.execute("UPDATE library_match_jobs SET status='completed',result_json=?,analysis_run_id=?,updated_at=? WHERE id=?",
                             (encode(output), history['id'], now(), job_id))
        except Exception as exc:
            LOG.exception('Library matching failed: %s', job_id)
            message = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
            with db() as conn:
                conn.execute("UPDATE library_match_jobs SET status='failed',error=?,updated_at=? WHERE id=?",
                             (message[:500] or '匹配执行失败，请查看 logs/peaknet-worker.log。', now(), job_id))

    @app.post('/api/library-matching/jobs')
    def create(payload: MatchRequest, user=Depends(auth)):
        profile, paths, source, name, project, cropped = validated(payload, user)
        settings = dict(top_k=payload.top_k, preprocessing_mode=payload.preprocessing_mode)
        job_id = uuid.uuid4().hex
        with gate:
            with db() as conn:
                count = conn.execute("SELECT COUNT(*) AS n FROM library_match_jobs WHERE status IN ('queued','running')").fetchone()['n']
                if count >= 3:
                    raise HTTPException(429, '匹配队列已满，请稍后重试。')
                conn.execute('''INSERT INTO library_match_jobs
                    (id,user_id,project_id,source_name,status,input_json,profile_json,settings_json,result_json,error,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (job_id, user['id'], project, name, 'queued', encode(dict(source=source, cropped=cropped)),
                     encode(profile), encode(settings), '{}', '', now(), now()))
            try:
                pool.submit(run, job_id, dict(user), paths)
            except RuntimeError:
                with db() as conn:
                    conn.execute("UPDATE library_match_jobs SET status='failed',error=? WHERE id=?", ('执行服务已关闭。', job_id))
                raise HTTPException(503, '执行服务已关闭。')
        with db() as conn:
            return decode(job_row(conn, job_id, user))

    @app.get('/api/library-matching/jobs')
    def jobs(user=Depends(auth)):
        with db() as conn:
            rows = conn.execute('SELECT * FROM library_match_jobs WHERE user_id=? ORDER BY created_at DESC LIMIT 30', (user['id'],)).fetchall()
            visible = []
            for row in rows:
                try:
                    job_row(conn, row['id'], user)
                except HTTPException:
                    continue
                visible.append(decode(row, False))
            return visible

    @app.get('/api/library-matching/jobs/{job_id}')
    def get_job(job_id: str, user=Depends(auth)):
        with db() as conn:
            return decode(job_row(conn, job_id, user))

    @app.get('/api/library-matching/jobs/{job_id}/download')
    def download(job_id: str, format: str = 'json', user=Depends(auth)):
        with db() as conn:
            value = decode(job_row(conn, job_id, user))
        if value['status'] != 'completed':
            raise HTTPException(400, '匹配尚未完成。')
        if format == 'json':
            return h['attachment_response'](encode(value).encode(), 'library_match.json', 'application/json')
        stream = io.StringIO()
        if format == 'csv':
            writer = csv.writer(stream)
            writer.writerow(['rank', 'material_id', 'name', 'model_score_closed_set_softmax'])
            writer.writerows([[c['rank'], c['class_id'], c['name'], c['model_score']] for c in value['result']['candidates']])
            return h['attachment_response'](stream.getvalue().encode('utf-8-sig'), 'library_match.csv', 'text/csv')
        if format == 'input':
            writer = csv.writer(stream, delimiter='\t')
            writer.writerow(['wavenumber', 'intensity'])
            spectrum = value['result']['model_input']
            writer.writerows(zip(spectrum['wavenumber'], spectrum['intensity']))
            return h['attachment_response'](stream.getvalue().encode(), 'peaknet_input.tsv', 'text/tab-separated-values')
        raise HTTPException(400, '仅支持 json、csv、input。')
