"""Folder imports and bounded batch execution of immutable spectrum plans."""
import io
import json
import logging
import uuid
import zipfile
from pathlib import PurePosixPath
from typing import List, Optional

from fastapi import Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

MAX_BATCH_FILES = 100
MAX_BATCH_BYTES = 40 * 1024 * 1024
LOG = logging.getLogger(__name__)


class BatchExecution(BaseModel):
    template_workflow_id: str
    template_version_id: str
    workflow_ids: List[str] = Field(..., min_items=1, max_items=MAX_BATCH_FILES)


def relative_name(value):
    path = PurePosixPath(value.replace('\\', '/'))
    if not value or path.is_absolute() or '..' in path.parts or any(':' in part or '\x00' in part for part in path.parts):
        raise ValueError('文件夹路径无效。')
    name = str(path)
    if len(name) > 240 or name == '.':
        raise ValueError('文件夹路径过长或为空。')
    return name


def install_ai_batches(app, h, core):
    db, now, auth = h['db_connect'], h['iso_now'], h['get_current_user']
    encode = lambda value: json.dumps(value, ensure_ascii=False, allow_nan=False)
    with db() as conn:
        conn.execute(f"""CREATE TABLE IF NOT EXISTS ai_workflow_batches (
            id {h['ID_SQL']} PRIMARY KEY, user_id {h['ID_SQL']} NOT NULL,
            name {h['NAME_SQL']} NOT NULL, created_at {h['DATE_SQL']} NOT NULL, updated_at {h['DATE_SQL']} NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) {h['TABLE_OPTIONS']}""")
        conn.execute(f"""CREATE TABLE IF NOT EXISTS ai_batch_items (
            id {h['ID_SQL']} PRIMARY KEY, batch_id {h['ID_SQL']} NOT NULL,
            position INTEGER NOT NULL, relative_path {h['NAME_SQL']} NOT NULL,
            workflow_id {h['ID_SQL']}, version_id {h['ID_SQL']},
            status {h['SHORT_SQL']} NOT NULL, error {h['JSON_SQL']} NOT NULL,
            FOREIGN KEY (batch_id) REFERENCES ai_workflow_batches(id) ON DELETE CASCADE
        ) {h['TABLE_OPTIONS']}""")
        h['create_index'](conn, 'idx_ai_batches_user', 'ai_workflow_batches', 'user_id')
        h['create_index'](conn, 'idx_ai_batch_items_batch', 'ai_batch_items', 'batch_id')
        h['create_index'](conn, 'idx_ai_batch_items_workflow', 'ai_batch_items', 'workflow_id')
        h['create_index'](conn, 'idx_ai_batch_items_version', 'ai_batch_items', 'version_id')

    def batch_row(conn, bid, user):
        row = conn.execute('SELECT * FROM ai_workflow_batches WHERE id = ?', (bid,)).fetchone()
        if row is None or row['user_id'] != user['id']:
            raise HTTPException(404, '批量任务不存在。')
        projects = conn.execute('SELECT DISTINCT w.project_id FROM ai_batch_items i JOIN ai_workflows w ON w.id=i.workflow_id WHERE i.batch_id=? AND w.project_id IS NOT NULL', (bid,)).fetchall()
        for p in projects:
            h['get_project_row'](conn, p['project_id'], user)
        return row

    def detail(bid, user):
        with db() as conn:
            row = batch_row(conn, bid, user)
            items = conn.execute('SELECT * FROM ai_batch_items WHERE batch_id = ? ORDER BY position', (bid,)).fetchall()
        items = [dict(item) for item in items]
        counts = {state: sum(item['status'] == state for item in items) for state in ('ready', 'invalid', 'queued', 'running', 'completed', 'failed', 'cancelled', 'deleted')}
        return dict(row, items=items, counts=counts, active=bool(counts['queued'] + counts['running']))

    @app.on_event('startup')
    def recover_batches():
        with db() as conn:
            items = conn.execute("SELECT id,version_id FROM ai_batch_items WHERE status IN ('queued','running')").fetchall()
            for item in items:
                version = conn.execute('SELECT status,error FROM ai_plan_versions WHERE id = ?', (item['version_id'],)).fetchone()
                status = 'completed' if version and version['status'] == 'completed' else 'failed'
                error = '' if status == 'completed' else '服务重启，批量执行中断，可重新提交。'
                conn.execute('UPDATE ai_batch_items SET status = ?, error = ? WHERE id = ?', (status, error, item['id']))

    @app.get('/api/ai-workflow-batches')
    def list_batches(user=Depends(auth)):
        with db() as conn:
            rows = conn.execute('SELECT id,name,created_at,updated_at FROM ai_workflow_batches WHERE user_id = ? ORDER BY updated_at DESC LIMIT 30', (user['id'],)).fetchall()
            visible = []
            for row in rows:
                try:
                    batch_row(conn, row['id'], user)
                    visible.append(dict(row))
                except HTTPException as exc:
                    if exc.status_code != 404:
                        raise
        return visible

    @app.post('/api/ai-workflow-batches/upload')
    async def upload_folder(files: List[UploadFile] = File(...), paths: List[str] = Form(...), project_id: Optional[str] = Form(None), confirm_conversion: bool = Form(False), dataset_ids: Optional[List[str]] = Form(None), user=Depends(auth)):
        if not 1 <= len(files) <= MAX_BATCH_FILES or len(files) != len(paths):
            raise HTTPException(400, '每批需包含 1～100 个文件，路径与文件数量必须一致。')
        try:
            names = [relative_name(path) for path in paths]
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        if len(set(names)) != len(names):
            raise HTTPException(400, '文件夹中存在重复路径。')
        if project_id:
            with db() as conn:
                h['get_project_row'](conn, project_id, user)
        contents, total = [], 0
        for file in files:
            content = await file.read(core['max_upload'] + 1)
            total += len(content)
            if total > MAX_BATCH_BYTES:
                raise HTTPException(400, '每批上传总大小不能超过 40 MB。')
            contents.append(content)
        if dataset_ids is not None:
            if not project_id or len(dataset_ids) != len(files):
                raise HTTPException(400, '项目文件数量与来源标识不一致。')
            with db() as conn:
                h['get_project_row'](conn, project_id, user)
                for did, content in zip(dataset_ids, contents):
                    asset = conn.execute('SELECT * FROM data_assets WHERE id=? AND project_id=?', (did,project_id)).fetchone()
                    if asset is None:
                        raise HTTPException(404, '项目来源文件不存在。')
                    if content != h['read_stored_file'](asset['storage_path']):
                        raise HTTPException(400, '文件内容与项目来源不一致，请重新选择。')
        inspections, previews = [], []
        for name, content in zip(names, contents):
            try:
                prepared = await run_in_threadpool(core['inspect_source'], content, name)
                if prepared[2].get('selection_required'):
                    raise HTTPException(400, '此文件含多条光谱，请单独上传选择位置，或先拆分后批量上传。')
                inspections.append((prepared, ''))
                previews.append(dict(core['import_preview'](prepared, name), relative_path=name, status='valid'))
            except HTTPException as exc:
                error = str(exc.detail)[:300]
                inspections.append((None, error))
                previews.append(dict(source_name=name, relative_path=name, status='invalid', error=error))
        if not confirm_conversion and any(item.get('requires_confirmation') for item in previews):
            return dict(requires_confirmation=True, items=previews,
                        conversion_count=sum(bool(item.get('requires_confirmation')) for item in previews))
        bid, timestamp = uuid.uuid4().hex, now()
        root = PurePosixPath(names[0]).parts[0]
        with db() as conn:
            conn.execute('INSERT INTO ai_workflow_batches (id,user_id,name,created_at,updated_at) VALUES (?,?,?,?,?)', (bid, user['id'], root, timestamp, timestamp))
        for index, (name, content, inspection) in enumerate(zip(names, contents, inspections)):
            workflow_id, status, error = None, 'ready', ''
            try:
                prepared, validation_error = inspection
                if validation_error:
                    raise HTTPException(400, validation_error)
                workflow_id = (await run_in_threadpool(core['create_task'], content, name, user, project_id, dataset_ids[index] if dataset_ids else None, confirm_conversion, prepared))['id']
            except HTTPException as exc:
                status, error = 'invalid', str(exc.detail)[:300]
            except Exception:
                LOG.exception('Batch source import failed: %s item %s', bid, index)
                status, error = 'invalid', '文件存储失败，请检查存储服务后重新上传。'
            with db() as conn:
                conn.execute('INSERT INTO ai_batch_items (id,batch_id,position,relative_path,workflow_id,status,error) VALUES (?,?,?,?,?,?,?)',
                    (uuid.uuid4().hex, bid, index, name, workflow_id, status, error))
        return detail(bid, user)

    @app.get('/api/ai-workflow-batches/{bid}')
    def get_batch(bid: str, user=Depends(auth)):
        return detail(bid, user)

    def remove_members(conn, members, user):
        """Validate every member before removing any part of a selected batch."""
        from history_resources import delete_artifacts
        workflow_ids = {item['workflow_id'] for item in members if item['workflow_id']}
        tasks, run_ids, locations = [], set(), []
        if any(item['status'] in ('queued', 'running') for item in members):
            raise HTTPException(409, '任务正在运行，暂不能删除。')
        for wid in workflow_ids:
            task = core['task_row'](conn, wid, user)
            tasks.append(task)
            versions = conn.execute('SELECT status,analysis_run_id FROM ai_plan_versions WHERE workflow_id=?', (wid,)).fetchall()
            if any(version['status'] in ('queued','running','previewing') for version in versions):
                raise HTTPException(409, '任务正在运行，暂不能删除。')
            run_ids.update(version['analysis_run_id'] for version in versions if version['analysis_run_id'])
        for row in conn.execute('SELECT id,result_json FROM analysis_runs WHERE user_id=?', (user['id'],)).fetchall():
            if json.loads(row['result_json']).get('ai_workflow_id') in workflow_ids:
                run_ids.add(row['id'])
        for rid in run_ids:
            conn.execute('UPDATE analysis_runs SET updated_at=updated_at WHERE id=?', (rid,))
            row = conn.execute('SELECT user_id FROM analysis_runs WHERE id=?', (rid,)).fetchone()
            if row and row['user_id'] != user['id']:
                raise HTTPException(403, '不能删除他人的记录。')
            if conn.execute('SELECT run_id FROM project_result_shares WHERE run_id=?', (rid,)).fetchone():
                raise HTTPException(409, '批次中有已共享结果，请先取消项目共享。')
        for rid in run_ids:
            locations.extend(delete_artifacts(h, conn, rid))
            conn.execute('DELETE FROM analysis_versions WHERE run_id=?', (rid,))
            conn.execute('DELETE FROM analysis_runs WHERE id=?', (rid,))
        for task in tasks:
            wid = task['id']
            conn.execute('DELETE FROM ai_plan_metadata WHERE version_id IN (SELECT id FROM ai_plan_versions WHERE workflow_id=?)', (wid,))
            conn.execute('DELETE FROM ai_plan_versions WHERE workflow_id=?', (wid,))
            conn.execute('DELETE FROM ai_workflow_origins WHERE workflow_id=?', (wid,))
            conn.execute('DELETE FROM ai_workflows WHERE id=?', (wid,))
            locations.append(task['storage_path'])
        for item in members:
            conn.execute("UPDATE ai_batch_items SET workflow_id=NULL,version_id=NULL,status='deleted',error='' WHERE id=?", (item['id'],))
        # A project source or another snapshot may still own the same file.
        return [location for location in set(locations) if not (
            conn.execute('SELECT id FROM data_assets WHERE storage_path=? LIMIT 1', (location,)).fetchone() or
            conn.execute('SELECT id FROM ai_workflows WHERE storage_path=? LIMIT 1', (location,)).fetchone() or
            conn.execute('SELECT run_id FROM analysis_array_files WHERE storage_path=? LIMIT 1', (location,)).fetchone())]

    @app.delete('/api/ai-workflow-batches/{bid}/items/{item_id}')
    def delete_member(bid: str, item_id: str, user=Depends(auth)):
        with core['gate'], db() as conn:
            batch_row(conn, bid, user)
            item = conn.execute('SELECT * FROM ai_batch_items WHERE batch_id=? AND (id=? OR workflow_id=?)', (bid,item_id,item_id)).fetchone()
            if item is None:
                raise HTTPException(404, '批次文件不存在。')
            locations = remove_members(conn, [item], user)
            conn.execute('UPDATE ai_workflow_batches SET updated_at=? WHERE id=?', (now(),bid))
        for location in locations:
            h['remove_stored_file'](location)
        return dict(deleted=True)

    @app.delete('/api/ai-workflow-batches/{bid}')
    def delete_batch(bid: str, user=Depends(auth)):
        with core['gate'], db() as conn:
            batch_row(conn, bid, user)
            members = conn.execute('SELECT * FROM ai_batch_items WHERE batch_id=?', (bid,)).fetchall()
            locations = remove_members(conn, members, user)
            conn.execute('DELETE FROM ai_batch_items WHERE batch_id=?', (bid,))
            conn.execute('DELETE FROM ai_workflow_batches WHERE id=?', (bid,))
        for location in locations:
            h['remove_stored_file'](location)
        return dict(deleted=True)

    def worker(bid, user):
        try:
            with db() as conn:
                items = conn.execute("SELECT * FROM ai_batch_items WHERE batch_id = ? AND status = 'queued' ORDER BY position", (bid,)).fetchall()
            for item in items:
                with core['gate'], db() as conn:
                    current = conn.execute('SELECT status,version_id FROM ai_batch_items WHERE id = ?', (item['id'],)).fetchone()
                    if current is None or current['status'] != 'queued' or current['version_id'] != item['version_id']:
                        continue
                    task = dict(core['task_row'](conn, item['workflow_id'], user))
                    version = core['decode_version'](core['version_row'](conn, item['workflow_id'], item['version_id']))
                    conn.execute("UPDATE ai_batch_items SET status = 'running' WHERE id = ?", (item['id'],))
                    conn.execute("UPDATE ai_plan_versions SET status = 'running', updated_at = ? WHERE id = ?", (now(), item['version_id']))
                core['execute_worker'](task, version, user)
                with db() as conn:
                    result = core['version_row'](conn, item['workflow_id'], item['version_id'])
                    conn.execute('UPDATE ai_batch_items SET status = ?, error = ? WHERE id = ?', (result['status'], result['error'], item['id']))
                    conn.execute('UPDATE ai_workflow_batches SET updated_at = ? WHERE id = ?', (now(), bid))
        except Exception:
            LOG.exception('Batch execution interrupted: %s', bid)
            fail_pending(bid, '批量执行服务异常，可重新提交。')

    def fail_pending(bid, message):
        with core['gate'], db() as conn:
            rows = conn.execute("SELECT version_id FROM ai_batch_items WHERE batch_id = ? AND status IN ('queued','running')", (bid,)).fetchall()
            for row in rows:
                conn.execute("UPDATE ai_plan_versions SET status = 'failed', error = ?, updated_at = ? WHERE id = ? AND status IN ('queued','running')", (message, now(), row['version_id']))
            conn.execute("UPDATE ai_batch_items SET status = 'failed', error = ? WHERE batch_id = ? AND status IN ('queued','running')", (message, bid))

    @app.post('/api/ai-workflow-batches/{bid}/execute')
    def execute_batch(bid: str, payload: BatchExecution, user=Depends(auth)):
        ids = payload.workflow_ids
        if len(set(ids)) != len(ids):
            raise HTTPException(400, '不能重复选择同一光谱。')
        with core['gate']:
            with db() as conn:
                batch_row(conn, bid, user)
                items = conn.execute('SELECT * FROM ai_batch_items WHERE batch_id = ? ORDER BY position', (bid,)).fetchall()
                if any(item['status'] in ('queued', 'running') for item in items):
                    raise HTTPException(409, '本批任务正在执行，请等待完成或停止待执行项。')
                selected = [item for item in items if item['workflow_id'] in ids]
                if len(selected) != len(ids):
                    raise HTTPException(404, '所选光谱不属于本批任务。')
                core['task_row'](conn, payload.template_workflow_id, user)
                template = core['decode_version'](core['version_row'](conn, payload.template_workflow_id, payload.template_version_id))
                if template['status'] in ('queued', 'running', 'previewing'):
                    raise HTTPException(409, '请等待当前方案处理完成。')
                if core['queue_size'](conn) >= 8:
                    raise HTTPException(429, '执行队列已满，请稍后重试。')
                for item in selected:
                    core['task_row'](conn, item['workflow_id'], user)
                    if conn.execute("SELECT id FROM ai_plan_versions WHERE workflow_id = ? AND status IN ('queued','running','previewing')", (item['workflow_id'],)).fetchone():
                        raise HTTPException(409, '所选光谱已有正在执行的任务。')
            queued = 0
            for item in selected:
                try:
                    with db() as conn:
                        latest = conn.execute('SELECT id FROM ai_plan_versions WHERE workflow_id = ? ORDER BY created_at DESC,id DESC LIMIT 1', (item['workflow_id'],)).fetchone()
                    version = core['new_version'](item['workflow_id'], user, template['goal'], template['steps'],
                        latest['id'] if latest else None, feedback=template['feedback'], provider=template['provider'], summary='批量应用方案：' + template['id'],
                        fallback_reason=template['fallback_reason'], metadata=dict(phase=template['metadata'].get('phase', 'preprocess'),
                            region=template['metadata'].get('region'), batch_id=bid, template_workflow_id=payload.template_workflow_id,
                            template_version_id=template['id']))
                    with db() as conn:
                        conn.execute("UPDATE ai_plan_versions SET status = 'queued', updated_at = ? WHERE id = ?", (now(), version['id']))
                        conn.execute("UPDATE ai_batch_items SET version_id = ?, status = 'queued', error = '' WHERE id = ?", (version['id'], item['id']))
                    queued += 1
                except HTTPException as exc:
                    with db() as conn:
                        conn.execute("UPDATE ai_batch_items SET version_id = NULL, status = 'failed', error = ? WHERE id = ?", (str(exc.detail)[:300], item['id']))
            with db() as conn:
                conn.execute('UPDATE ai_workflow_batches SET updated_at = ? WHERE id = ?', (now(), bid))
        if queued:
            try:
                core['pool'].submit(worker, bid, user)
            except RuntimeError:
                fail_pending(bid, '执行服务不可用，请稍后重试。')
                raise HTTPException(503, '执行服务不可用。')
        return detail(bid, user)

    @app.post('/api/ai-workflow-batches/{bid}/cancel')
    def cancel_pending(bid: str, user=Depends(auth)):
        with core['gate'], db() as conn:
            batch_row(conn, bid, user)
            rows = conn.execute("SELECT version_id FROM ai_batch_items WHERE batch_id = ? AND status = 'queued'", (bid,)).fetchall()
            for row in rows:
                conn.execute("UPDATE ai_plan_versions SET status = 'failed', error = ?, updated_at = ? WHERE id = ? AND status = 'queued'", ('用户停止了待执行的批量任务。', now(), row['version_id']))
            conn.execute("UPDATE ai_batch_items SET status = 'cancelled', error = ? WHERE batch_id = ? AND status = 'queued'", ('已停止，当前正在计算的项不受影响。', bid))
        return detail(bid, user)

    @app.get('/api/ai-workflow-batches/{bid}/download')
    def download_batch(bid: str, user=Depends(auth)):
        batch = detail(bid, user)
        if batch['active']:
            raise HTTPException(409, '请等待本批任务完成或停止待执行项后下载。')
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr('manifest.json', encode(batch))
            for item in batch['items']:
                if item['status'] != 'completed' or not item['version_id']:
                    continue
                with db() as conn:
                    core['task_row'](conn, item['workflow_id'], user)
                    version = core['decode_version'](core['version_row'](conn, item['workflow_id'], item['version_id']))
                name = f"{item['position'] + 1:03d}_" + h['clean_storage_name'](PurePosixPath(item['relative_path']).stem)
                bundle.writestr(name + '/result.txt', h['spectrum_result_content'](version['trace'][-1]['after']))
                bundle.writestr(name + '/workflow.json', encode({key: version[key] for key in ('id', 'goal', 'steps', 'metadata', 'analysis_run_id')}))
        return h['attachment_response'](buffer.getvalue(), 'raman_batch_results.zip', 'application/zip')
