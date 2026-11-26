"""Durable, owner-scoped local SSnet training and mixture extraction jobs."""
import csv
import io
import json
import os
import sys
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from ssnet_contract import ACTIVE, PYTHON, ROOT, SSNET_DEVICE, align, prepare_standards, runtime_ready
from module_records import ModuleRecords


class Source(BaseModel):
    source_id: Optional[str] = Field(None, max_length=64)
    workflow_id: Optional[str] = Field(None, max_length=64)
    version_id: Optional[str] = Field(None, max_length=64)


class Training(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    standards: List[Source] = Field(..., min_items=1, max_items=20)
    unit_confirmed: bool = False
    start: Optional[float] = None
    end: Optional[float] = None
    points: int = Field(1024, ge=128, le=4096)
    epochs: int = Field(100, ge=1, le=200)
    samples_per_epoch: int = Field(3200, ge=32, le=3200)
    batch_size: int = Field(4, ge=2, le=8)
    rf_samples: int = Field(4000, ge=32, le=4000)
    trees: int = Field(500, ge=10, le=500)
    device: str = Field(SSNET_DEVICE, regex='^(cpu|cuda)$')


class Prediction(Source):
    model_id: str = Field(..., max_length=64)
    unit_confirmed: bool = False


def execute_local(directory, request, update, cancelled):
    """One owned child per job; terminating it also cancels training/RF work."""
    directory.mkdir(parents=True, exist_ok=True)
    request_path = directory / 'request.json'
    request_path.write_text(json.dumps(request, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    env = dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', MPLBACKEND='Agg', PYTHONUTF8='1')
    with (directory / 'worker.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([str(PYTHON), str(ROOT / 'services/ssnet/worker.py'), str(request_path)],
                                   stdout=log, stderr=log, env=env,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            last = None
            while process.poll() is None:
                if cancelled.is_set():
                    return None
                progress_file = directory / 'progress.json'
                try:
                    current = progress_file.read_text(encoding='utf-8')
                    if current != last:
                        update(json.loads(current))
                        last = current
                except (OSError, ValueError):
                    pass
                cancelled.wait(.5)
            if cancelled.is_set():
                return None
            output_path = directory / 'output.json'
            if process.returncode or not output_path.exists():
                error_path = directory / 'error.json'
                message = json.loads(error_path.read_text(encoding='utf-8'))['error'] if error_path.exists() else '本地 SSnet 执行失败，请查看任务日志。'
                raise RuntimeError(message)
            return json.loads(output_path.read_text(encoding='utf-8'))
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def install_ssnet(app, h):
    db, now, auth = h['db_connect'], h['iso_now'], h['get_current_user']
    encode = lambda v: json.dumps(v, ensure_ascii=False, allow_nan=False)
    folder = h['STORAGE_DIR'] / 'ssnet'
    gate, events = threading.RLock(), {}
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='ssnet')
    with db() as conn:
        conn.execute(f'''CREATE TABLE IF NOT EXISTS ssnet_jobs (
            id {h['ID_SQL']} PRIMARY KEY, user_id {h['ID_SQL']} NOT NULL,
            kind {h['SHORT_SQL']} NOT NULL, name {h['NAME_SQL']} NOT NULL,
            status {h['SHORT_SQL']} NOT NULL, input_json {h['JSON_SQL']} NOT NULL,
            result_json {h['JSON_SQL']} NOT NULL, progress_json {h['JSON_SQL']} NOT NULL,
            error {h['JSON_SQL']} NOT NULL, created_at {h['DATE_SQL']} NOT NULL, updated_at {h['DATE_SQL']} NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) {h['TABLE_OPTIONS']}''')
        h['create_index'](conn, 'idx_ssnet_owner', 'ssnet_jobs', 'user_id')
        conn.execute(f'''CREATE TABLE IF NOT EXISTS ssnet_completions (
            job_id {h['ID_SQL']} PRIMARY KEY, read_at {h['DATE_SQL']},
            FOREIGN KEY (job_id) REFERENCES ssnet_jobs(id) ON DELETE CASCADE
        ) {h['TABLE_OPTIONS']}''')

    @app.on_event('startup')
    def recover():
        with db() as conn:
            conn.execute("UPDATE ssnet_jobs SET status='failed',error=?,updated_at=? WHERE status='running'",
                         ('服务重启时任务中断。可使用原数据和参数重新排队。', now()))
            queued = conn.execute("SELECT id,user_id FROM ssnet_jobs WHERE status='queued' ORDER BY created_at,id").fetchall()
        with gate:
            for job in queued:
                enqueue(job['id'], job['user_id'])

    @app.on_event('shutdown')
    def shutdown():
        with gate:
            for event in events.values():
                event.set()
        pool.shutdown(wait=True, **({'cancel_futures': True} if sys.version_info >= (3, 9) else {}))

    def decode(row, detail=True):
        value = {k: row[k] for k in ('id', 'kind', 'name', 'status', 'error', 'created_at', 'updated_at')}
        result = json.loads(row['result_json'])
        value['analysis_run_id'] = result.pop('analysis_run_id', None)
        value.update(progress=json.loads(row['progress_json']))
        if detail:
            value.update(input=json.loads(row['input_json']), result=result)
        elif row['kind'] == 'train':
            value['grid'] = json.loads(row['input_json'])['prepared']['grid']
        return value

    def owned(conn, job_id, user):
        row = conn.execute('SELECT * FROM ssnet_jobs WHERE id=? AND user_id=?', (job_id, user['id'])).fetchone()
        if row is None:
            raise HTTPException(404, 'SSnet 记录不存在。')
        # Recheck every project referenced by either the source or the model standards.
        for project in json.loads(row['input_json']).get('projects', []):
            h['get_project_row'](conn, project, user)
        return row

    records = ModuleRecords(app, h, 'ssnet', 'ssnet', owned, decode)

    def freeze(refs, user):
        sources, projects, names = [], set(), []
        with db() as conn:
            for ref in refs:
                source, name, project = records.input(conn, ref, user)
                sources.append(source)
                names.append(name)
                if project:
                    projects.add(project)
        return sources, names, sorted(projects)

    def training_input(payload, user):
        if not payload.unit_confirmed:
            raise HTTPException(400, '请先确认标准品横轴为拉曼位移 cm⁻¹。')
        if not payload.name.strip():
            raise HTTPException(400, '请输入标准品名称。')
        sources, names, projects = freeze(payload.standards, user)
        try:
            prepared = prepare_standards(sources, payload.dict())
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        settings = payload.dict(exclude={'standards', 'unit_confirmed'})
        if SSNET_DEVICE == 'cuda':
            settings['device'] = SSNET_DEVICE
        return dict(settings=settings, sources=sources,
                    source_names=names, prepared=prepared, projects=projects)

    def prediction_input(payload, user):
        if not payload.unit_confirmed:
            raise HTTPException(400, '请先确认混合谱横轴为拉曼位移 cm⁻¹。')
        with db() as conn:
            model = decode(owned(conn, payload.model_id, user))
        if model['kind'] != 'train' or model['status'] != 'completed':
            raise HTTPException(400, '请选择已经训练完成的标准品模型。')
        sources, names, projects = freeze([payload], user)
        try:
            prepared = align(sources[0]['spectrum'], model['input']['prepared']['grid'])
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        from model_history import ssnet_training_parameters
        return dict(source=sources[0], source_names=names, prepared=prepared,
                    source_project_id=projects[0] if projects else None,
                    device=SSNET_DEVICE,
                    model_id=model['id'], model_name=model['name'], grid=model['input']['prepared']['grid'],
                    training_parameters=ssnet_training_parameters(model['input']['settings']),
                    network_sha256=model['result'].get('network_sha256'),
                    artifacts=model['result']['artifacts'], projects=sorted(set(projects + model['input']['projects'])))

    def run(job_id, user_id, cancel):
        directory = folder / job_id
        try:
            with gate:
                if cancel.is_set():
                    return
                with db() as conn:
                    account = conn.execute('SELECT * FROM users WHERE id=? AND is_active=1', (user_id,)).fetchone()
                    if account is None:
                        raise HTTPException(403, '账号已停用，任务未执行。')
                    user = h['row_to_user'](account)
                    row = owned(conn, job_id, user)
                    if row['status'] != 'queued':
                        return
                    conn.execute("UPDATE ssnet_jobs SET status='running',updated_at=? WHERE id=? AND status='queued'", (now(), job_id))
            value = decode(row)
            request = dict(kind=value['kind'], input=value['input'])
            if value['kind'] == 'predict':
                request['model_dir'] = str(folder / value['input']['model_id'])

            def update(progress):
                with db() as conn:
                    conn.execute("UPDATE ssnet_jobs SET progress_json=?,updated_at=? WHERE id=? AND status='running'", (encode(progress), now(), job_id))

            result = execute_local(directory, request, update, cancel)
            with gate:
                if cancel.is_set() or result is None:
                    return
                if value['kind'] == 'predict':
                    inputs = value['input']
                    source = inputs['source']
                    original = source['spectrum']
                    processing = dict(grid=inputs['grid'], normalization_scale=inputs['prepared']['scale'],
                                      training_parameters=inputs['training_parameters'])
                    output = dict(result, intensity=result['extracted'], job_id=job_id,
                                  model_id=inputs['model_id'], model_name=inputs['model_name'], processing=processing)
                    history = h['save_analysis_run'](user, 'mixture_analysis', value['input']['source_names'][0],
                        source.get('steps', []), original, output, [], title=value['name'],
                        project_id=value['input'].get('source_project_id'), result_filename='mixture_result.csv')
                    result = dict(result, analysis_run_id=history['id'])
                with db() as conn:
                    owned(conn, job_id, user)
                    conn.execute("UPDATE ssnet_jobs SET status='completed',result_json=?,progress_json=?,updated_at=? WHERE id=? AND status='running'",
                                 (encode(result), encode(dict(percent=100, stage='completed')), now(), job_id))
                    conn.execute('INSERT INTO ssnet_completions (job_id) VALUES (?)', (job_id,))
        except Exception as exc:
            with db() as conn:
                conn.execute("UPDATE ssnet_jobs SET status='failed',error=?,updated_at=? WHERE id=? AND status IN ('queued','running')",
                             (str(exc.detail if isinstance(exc, HTTPException) else exc)[:500], now(), job_id))
        finally:
            with gate:
                events.pop(job_id, None)

    def enqueue(job_id, user_id):
        cancel = threading.Event()
        events[job_id] = cancel
        try:
            pool.submit(run, job_id, user_id, cancel)
        except RuntimeError as exc:
            events.pop(job_id, None)
            raise HTTPException(503, 'SSnet 服务正在关闭，请稍后重试。') from exc

    def create(kind, name, value, user, *, retry_id=None):
        if not runtime_ready():
            raise HTTPException(503, '本地模型环境未安装，请按 MIXTURE_ANALYSIS.md 准备环境。')
        job_id = retry_id or uuid.uuid4().hex
        with gate:
            with db() as conn:
                if retry_id and conn.execute('SELECT id FROM ssnet_jobs WHERE id=? AND user_id=?', (job_id, user['id'])).fetchone():
                    return decode(owned(conn, job_id, user))
                n = conn.execute("SELECT COUNT(*) AS n FROM ssnet_jobs WHERE status IN ('queued','running')").fetchone()['n']
                if n >= 3:
                    raise HTTPException(429, '本地 SSnet 队列已满，请等待或停止已有任务。')
                conn.execute('''INSERT INTO ssnet_jobs (id,user_id,kind,name,status,input_json,result_json,progress_json,error,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (job_id,user['id'],kind,name,'queued',encode(value),'{}',encode(dict(percent=0,stage='queued')),'',now(),now()))
            enqueue(job_id, user['id'])
        with db() as conn:
            return decode(owned(conn, job_id, user))

    @app.get('/api/ssnet/config')
    def config(user=Depends(auth)):
        return dict(ready=runtime_ready(), algorithm='SSnet · U-Net ECA + Random Forest', device=SSNET_DEVICE,
                    message='SSnet 任务按提交顺序在服务器处理。关闭网页后仍会继续。')

    @app.post('/api/ssnet/train/validate')
    def validate_train(payload: Training, user=Depends(auth)):
        value = training_input(payload, user)
        return dict(grid=value['prepared']['grid'], standards=len(value['sources']), source_names=value['source_names'])

    @app.post('/api/ssnet/predict/validate')
    def validate_predict(payload: Prediction, user=Depends(auth)):
        value = prediction_input(payload, user)
        return dict(grid=value['grid'], model_name=value['model_name'], prepared=value['prepared'])

    @app.post('/api/ssnet/train')
    def train(payload: Training, user=Depends(auth)):
        return create('train', payload.name.strip(), training_input(payload, user), user)

    @app.post('/api/ssnet/predict')
    def predict(payload: Prediction, user=Depends(auth)):
        value = prediction_input(payload, user)
        return create('predict', value['source_names'][0], value, user)

    @app.get('/api/ssnet/completions')
    def completions(user=Depends(auth)):
        with db() as conn:
            rows = conn.execute('''SELECT j.id,j.kind,j.name FROM ssnet_jobs j JOIN ssnet_completions c ON c.job_id=j.id
                WHERE j.user_id=? AND j.status='completed' AND c.read_at IS NULL ORDER BY j.updated_at DESC,j.id DESC''',
                (user['id'],)).fetchall()
            visible = []
            for row in rows:
                try:
                    owned(conn, row['id'], user)
                except HTTPException:
                    continue
                visible.append(dict(row))
            return visible

    @app.get('/api/ssnet/jobs')
    def jobs(user=Depends(auth)):
        with db() as conn:
            rows = conn.execute('SELECT * FROM ssnet_jobs WHERE user_id=? ORDER BY created_at DESC', (user['id'],)).fetchall()
            visible = []
            for row in rows:
                try:
                    owned(conn, row['id'], user)
                except HTTPException:
                    continue
                visible.append(decode(row, False))
            return visible

    @app.get('/api/ssnet/jobs/{job_id}')
    def get(job_id: str, user=Depends(auth)):
        with db() as conn:
            value = decode(owned(conn, job_id, user))
            if value['status'] == 'queued':
                ahead = conn.execute("""SELECT COUNT(*) AS n FROM ssnet_jobs WHERE status='queued'
                    AND (created_at<? OR (created_at=? AND id<?))""", (value['created_at'], value['created_at'], job_id)).fetchone()['n']
                value['queue_position'] = ahead + 1
            return value

    @app.post('/api/ssnet/jobs/{job_id}/seen')
    def seen(job_id: str, user=Depends(auth)):
        with db() as conn:
            owned(conn, job_id, user)
            conn.execute('UPDATE ssnet_completions SET read_at=? WHERE job_id=? AND read_at IS NULL', (now(), job_id))
        return {'seen': True}

    @app.post('/api/ssnet/jobs/{job_id}/retry')
    def retry(job_id: str, user=Depends(auth)):
        with db() as conn:
            original = owned(conn, job_id, user)
            if original['status'] not in ('cancelled', 'failed'):
                raise HTTPException(409, '只有已取消或失败的任务可以重新排队。')
            value = decode(original)
            inputs = value['input']
            if value['kind'] == 'train' and SSNET_DEVICE == 'cuda':
                inputs['settings']['device'] = SSNET_DEVICE
            if value['kind'] == 'predict':
                model = owned(conn, inputs['model_id'], user)
                if model['status'] != 'completed':
                    raise HTTPException(400, '原标准品模型已不可用，请重新选择。')
                inputs['device'] = SSNET_DEVICE
        retry_id = uuid.uuid5(uuid.NAMESPACE_URL, f'ramancloud.ssnet.retry/{job_id}').hex
        return create(value['kind'], value['name'], inputs, user, retry_id=retry_id)

    @app.post('/api/ssnet/jobs/{job_id}/cancel')
    def cancel(job_id: str, user=Depends(auth)):
        with gate:
            with db() as conn:
                row = owned(conn, job_id, user)
                if row['status'] not in ACTIVE:
                    raise HTTPException(409, '该任务已经结束。')
                if job_id in events:
                    events[job_id].set()
                conn.execute("UPDATE ssnet_jobs SET status='cancelled',updated_at=? WHERE id=?", (now(), job_id))
            return get(job_id, user)

    @app.get('/api/ssnet/jobs/{job_id}/download')
    def download(job_id: str, format: str = 'json', user=Depends(auth)):
        value = get(job_id, user)
        if format == 'json':
            return h['attachment_response'](encode(value).encode(), 'ssnet_record.json', 'application/json')
        if format == 'csv' and value['kind'] == 'predict' and value['status'] == 'completed':
            result = value['result']
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(['raman_shift_cm-1','mixture_min_shifted','extracted_target','estimated_background'])
            writer.writerows(zip(result['wavenumber'],result['mixture'],result['extracted'],result['background']))
            return h['attachment_response'](stream.getvalue().encode('utf-8-sig'), 'ssnet_spectra.csv', 'text/csv')
        raise HTTPException(400, 'CSV 仅用于已经完成的混合谱解析；其他记录可导出 JSON。')
