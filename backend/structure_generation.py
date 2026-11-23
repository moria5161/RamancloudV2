"""Authenticated, persistent structure generation jobs with frozen spectrum provenance."""
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

from structure_profiles import configuration, formula_counts, prepare_spectrum, public_configuration
from structure_runtime import LocalRuntime
from module_records import ModuleRecords

LOG = logging.getLogger(__name__)
RUNTIME = LocalRuntime()


class GenerationRequest(BaseModel):
    source_id: Optional[str] = Field(None, max_length=64)
    engine: str = Field('official', regex='^(official|agent)$')
    workflow_id: Optional[str] = Field(None, max_length=64)
    version_id: Optional[str] = Field(None, max_length=64)
    reuse_job_id: Optional[str] = Field(None, max_length=64)
    unit_confirmed: bool = False
    formula: str = Field('', max_length=120)
    top_k: int = Field(5, ge=1, le=10)
    rerank: bool = True


def install_structure_generation(app, h):
    db, now, auth = h['db_connect'], h['iso_now'], h['get_current_user']
    encode = lambda value: json.dumps(value, ensure_ascii=False, allow_nan=False)
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='vib2mol')
    gate = threading.Lock()
    with db() as conn:
        conn.execute(f"""CREATE TABLE IF NOT EXISTS structure_jobs (
            id {h['ID_SQL']} PRIMARY KEY, user_id {h['ID_SQL']} NOT NULL, project_id {h['ID_SQL']},
            source_name {h['NAME_SQL']} NOT NULL, status {h['SHORT_SQL']} NOT NULL,
            input_json {h['JSON_SQL']} NOT NULL, profile_json {h['JSON_SQL']} NOT NULL,
            settings_json {h['JSON_SQL']} NOT NULL, result_json {h['JSON_SQL']} NOT NULL,
            error {h['JSON_SQL']} NOT NULL, analysis_run_id {h['ID_SQL']},
            created_at {h['DATE_SQL']} NOT NULL, updated_at {h['DATE_SQL']} NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) {h['TABLE_OPTIONS']}""")
        h['create_index'](conn, 'idx_structure_jobs_user', 'structure_jobs', 'user_id')

    @app.on_event('startup')
    def recover():
        with db() as conn:
            conn.execute("UPDATE structure_jobs SET status='failed', error=?, updated_at=? WHERE status IN ('queued','running')",
                         ('服务重启，推理中断。请重新生成。', now()))

    @app.on_event('shutdown')
    def shutdown():
        RUNTIME.close()
        pool.shutdown(wait=False, **({'cancel_futures': True} if sys.version_info >= (3, 9) else {}))

    def job_row(conn, job_id, user):
        row = conn.execute('SELECT * FROM structure_jobs WHERE id=? AND user_id=?', (job_id, user['id'])).fetchone()
        if row is None:
            raise HTTPException(404, '生成任务不存在。')
        if row['project_id']:
            h['get_project_row'](conn, row['project_id'], user)
        return row

    def decode(row, detail=True):
        value = {key: row[key] for key in ('id', 'source_name', 'status', 'error', 'analysis_run_id', 'created_at', 'updated_at')}
        for key in ('profile', 'settings'):
            value[key] = json.loads(row[key + '_json'])
        if detail:
            value.update(input=json.loads(row['input_json']), result=json.loads(row['result_json']))
        return value

    records = ModuleRecords(app, h, 'structure-generation', 'structure', job_row, decode)

    def freeze_source(payload, user):
        if not payload.unit_confirmed:
            raise HTTPException(400, '请先确认横轴是拉曼位移 cm⁻¹。')
        with db() as conn:
            if payload.reuse_job_id:
                old = job_row(conn, payload.reuse_job_id, user)
                return json.loads(old['input_json'])['source'], old['source_name'], old['project_id']
            return records.input(conn, payload, user)

    def validated(payload, user):
        source, name, project = freeze_source(payload, user)
        try:
            profile, paths = configuration(payload.engine)
            counts = formula_counts(payload.formula.strip())
            model_input = prepare_spectrum(source['spectrum'], profile)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return source, name, project, profile, paths, model_input, counts

    @app.get('/api/structure-generation/config')
    def get_config(engine: str = 'official', user=Depends(auth)):
        try:
            return public_configuration(engine)
        except (ValueError, OSError) as exc:
            raise HTTPException(503, '模型配置无效，请检查服务端配置。') from exc

    @app.post('/api/structure-generation/validate')
    def validate(payload: GenerationRequest, user=Depends(auth)):
        _, name, _, profile, _, prepared, _ = validated(payload, user)
        return dict(source_name=name, profile=profile, model_input=prepared)

    def run(job_id, user, paths):
        try:
            with db() as conn:
                row = job_row(conn, job_id, user)
                conn.execute("UPDATE structure_jobs SET status='running', updated_at=? WHERE id=?", (now(), job_id))
            value = decode(row)
            settings = value['settings']
            output = RUNTIME.infer(value['profile'], paths,
                                   dict(intensity=value['input']['model_input']['intensity'],
                                        formula_counts=formula_counts(settings['formula']),
                                        top_k=settings['top_k'], rerank=settings['rerank']))
            output['warnings'] = list(value['input']['model_input']['warnings'])
            if not output['candidates']:
                output['warnings'].append('本次没有满足条件的有效候选。可检查预处理或取消分子式筛选后重试；系统不会补入示例结构。')
            summary = dict(output, candidates=[{k: v for k, v in c.items() if k != 'sdf'} for c in output['candidates']],
                           job_id=job_id, profile=value['profile'], source_reference=value['input']['source']['reference'])
            with db() as conn:
                job_row(conn, job_id, user)  # Recheck membership before publishing history.
            history = h['save_analysis_run'](
                current_user=user, analysis_type='structure_generation', source_name=row['source_name'],
                steps=[dict(type='structure_generation', method='vib2mol', params=settings)],
                input_payload=value['input'], result_payload=summary,
                history=[dict(profile=value['profile'], duration_seconds=output['duration_seconds'])],
                title=row['source_name'] + ' · 光谱到结构', project_id=row['project_id'], result_filename='structure_result.json')
            with db() as conn:
                conn.execute("UPDATE structure_jobs SET status='completed', result_json=?, analysis_run_id=?, updated_at=? WHERE id=?",
                             (encode(output), history['id'], now(), job_id))
        except Exception as exc:
            LOG.exception('Structure inference failed: %s', job_id)
            message = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
            with db() as conn:
                conn.execute("UPDATE structure_jobs SET status='failed', error=?, updated_at=? WHERE id=?",
                             (message[:500] or '模型推理失败，请查看服务日志。', now(), job_id))

    @app.post('/api/structure-generation/jobs')
    def create(payload: GenerationRequest, user=Depends(auth)):
        source, name, project, profile, paths, prepared, _ = validated(payload, user)
        if not public_configuration(payload.engine)['ready']:
            raise HTTPException(503, '模型未安装，请按安装文档配置。')
        settings = dict(engine=payload.engine, formula=payload.formula.strip(), top_k=payload.top_k, rerank=payload.rerank)
        job_id = uuid.uuid4().hex
        with gate:
            with db() as conn:
                # Keep a CPU machine responsive and prevent an unbounded inference queue.
                count = conn.execute("SELECT COUNT(*) AS n FROM structure_jobs WHERE status IN ('queued','running')").fetchone()['n']
                if count >= 3:
                    raise HTTPException(429, '模型任务队列已满，请稍后重试。')
                conn.execute('''INSERT INTO structure_jobs
                    (id,user_id,project_id,source_name,status,input_json,profile_json,settings_json,result_json,error,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (job_id, user['id'], project, name, 'queued', encode(dict(source=source, model_input=prepared)),
                     encode(profile), encode(settings), '{}', '', now(), now()))
            try:
                pool.submit(run, job_id, dict(user), paths)
            except RuntimeError:
                with db() as conn:
                    conn.execute("UPDATE structure_jobs SET status='failed',error=? WHERE id=?", ('执行服务已关闭。', job_id))
                raise HTTPException(503, '执行服务已关闭。')
        with db() as conn:
            return decode(job_row(conn, job_id, user))

    @app.get('/api/structure-generation/jobs')
    def jobs(user=Depends(auth)):
        with db() as conn:
            rows = conn.execute('SELECT * FROM structure_jobs WHERE user_id=? ORDER BY created_at DESC LIMIT 30', (user['id'],)).fetchall()
            result = []
            for row in rows:
                try:
                    job_row(conn, row['id'], user)
                except HTTPException:
                    continue
                result.append(decode(row, False))
            return result

    @app.get('/api/structure-generation/jobs/{job_id}')
    def get_job(job_id: str, user=Depends(auth)):
        with db() as conn:
            return decode(job_row(conn, job_id, user))

    @app.get('/api/structure-generation/jobs/{job_id}/download')
    def download(job_id: str, format: str = 'json', user=Depends(auth)):
        with db() as conn:
            value = decode(job_row(conn, job_id, user))
        if value['status'] != 'completed':
            raise HTTPException(400, '任务尚未完成。')
        candidates = value['result']['candidates']
        if format == 'json':
            for c in candidates:
                c.pop('image_png', None)
            content, media = encode(value).encode(), 'application/json'
        elif format == 'csv':
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(['rank', 'smiles', 'formula', 'inchikey', 'matching_score', 'generation_score'])
            writer.writerows([[c[k] for k in ('rank', 'smiles', 'formula', 'inchikey', 'matching_score', 'generation_score')] for c in candidates])
            content, media = stream.getvalue().encode('utf-8-sig'), 'text/csv'
        elif format == 'sdf':
            content = ''.join(c['sdf'] + '\n> <rank>\n' + str(c['rank']) + '\n\n> <SMILES>\n' + c['smiles'] + '\n\n$$$$\n' for c in candidates).encode()
            media = 'chemical/x-mdl-sdfile'
        else:
            raise HTTPException(400, '仅支持 json、csv、sdf。')
        return h['attachment_response'](content, f'structure_{job_id}.{format}', media)
