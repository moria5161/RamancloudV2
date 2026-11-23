"""Independent spectrum inputs and named results for each analysis module."""
import hashlib
import json
import threading
import uuid
from typing import Optional

from fastapi import Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, constr

from spectral_formats import standard_spectrum_content
from workflow_spectrum import freeze_workflow_spectrum


class SaveResult(BaseModel):
    job_id: str = Field(..., min_length=1, max_length=64)
    title: constr(strip_whitespace=True, min_length=1, max_length=160)


class ModuleRecords:
    def __init__(self, app, h, slug, prefix, reader, decoder):
        # All table/path names are supplied by the server, never by a request.
        self.h, self.slug, self.prefix = h, slug, prefix
        self.sources, self.saved = prefix + '_sources', prefix + '_saved_results'
        self.reader, self.decoder = reader, decoder
        h.setdefault('_analysis_module_records', {})[slug] = self
        self.lock = threading.Lock()
        db, auth, now = h['db_connect'], h['get_current_user'], h['iso_now']
        encode = lambda value: json.dumps(value, ensure_ascii=False, allow_nan=False)
        with db() as conn:
            conn.execute(f'''CREATE TABLE IF NOT EXISTS {self.sources} (
                id {h['ID_SQL']} PRIMARY KEY, user_id {h['ID_SQL']} NOT NULL,
                project_id {h['ID_SQL']}, source_name {h['NAME_SQL']} NOT NULL,
                storage_path {h['PATH_SQL']} NOT NULL, original_json {h['JSON_SQL']} NOT NULL,
                diagnostics_json {h['JSON_SQL']} NOT NULL, created_at {h['DATE_SQL']} NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            ){h['TABLE_OPTIONS']}''')
            conn.execute(f'''CREATE TABLE IF NOT EXISTS {self.saved} (
                id {h['ID_SQL']} PRIMARY KEY, user_id {h['ID_SQL']} NOT NULL,
                job_id {h['ID_SQL']} NOT NULL UNIQUE, title {h['NAME_SQL']} NOT NULL,
                created_at {h['DATE_SQL']} NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            ){h['TABLE_OPTIONS']}''')
            h['create_index'](conn, 'idx_' + prefix + '_source_owner', self.sources, 'user_id,created_at')
            h['create_index'](conn, 'idx_' + prefix + '_saved_owner', self.saved, 'user_id,created_at')

        route = '/api/' + slug

        @app.post(route + '/sources/upload')
        async def upload(file: UploadFile = File(...), project_id: Optional[str] = Form(None),
                         confirm_conversion: bool = Form(False), spectrum_index: Optional[int] = Form(None), user=Depends(auth)):
            content = await file.read(4 * 1024 * 1024 + 1)
            name = file.filename or 'spectrum.txt'
            if project_id:
                with db() as conn:
                    h['get_project_row'](conn, project_id, user)
            prepared = h['_inspect_spectrum_upload'](content, name, spectrum_index)
            if prepared[2]['conversion_required'] and not confirm_conversion:
                return h['_spectrum_import_preview'](prepared, name)
            x, y, metadata = prepared
            if metadata.get('selection_required'):
                raise HTTPException(400, '请选择文件中的一条光谱后确认导入。')
            sid, stamp = uuid.uuid4().hex, now()
            metadata = dict(metadata, original_preserved=True, conversion_confirmed=confirm_conversion,
                            conversion_status='converted' if metadata['conversion_required'] else 'already_standard')
            metadata['standardized_sha256'] = hashlib.sha256(standard_spectrum_content(x, y)).hexdigest()
            diag = dict(h['_spectrum_diagnostics'](x, y), source_check=metadata)
            path = h['store_project_file'](prefix + '_inputs', sid, h['clean_storage_name'](name), content)
            try:
                with db() as conn:
                    if project_id:
                        h['get_project_row'](conn, project_id, user)
                    conn.execute(f'''INSERT INTO {self.sources}
                        (id,user_id,project_id,source_name,storage_path,original_json,diagnostics_json,created_at)
                        VALUES (?,?,?,?,?,?,?,?)''', (sid, user['id'], project_id, name[:240], path,
                        encode(dict(wavenumber=x.tolist(), intensity=y.tolist())), encode(diag), stamp))
                    return self.decode_source(self.source_row(conn, sid, user))
            except Exception:
                h['remove_stored_file'](path)
                raise

        @app.get(route + '/sources')
        def list_sources(user=Depends(auth)):
            with db() as conn:
                rows = conn.execute(f'SELECT id FROM {self.sources} WHERE user_id=? ORDER BY created_at DESC LIMIT 100', (user['id'],)).fetchall()
                result = []
                for row in rows:
                    try:
                        source = self.source_row(conn, row['id'], user)
                        result.append({key: source[key] for key in ('id', 'source_name', 'created_at')})
                    except HTTPException:
                        continue
                return result

        @app.get(route + '/sources/{source_id}')
        def get_source(source_id: str, user=Depends(auth)):
            with db() as conn:
                return self.decode_source(self.source_row(conn, source_id, user))

        @app.get(route + '/sources/{source_id}/download')
        def download_source(source_id: str, kind: str = 'original', user=Depends(auth)):
            with db() as conn:
                row = self.source_row(conn, source_id, user)
            if kind == 'original':
                return h['attachment_response'](h['read_stored_file'](row['storage_path']), row['source_name'])
            if kind == 'standardized':
                original = json.loads(row['original_json'])
                return h['attachment_response'](standard_spectrum_content(original['wavenumber'], original['intensity']), 'standardized_spectrum.txt')
            raise HTTPException(400, '不支持的下载类型。')

        @app.post(route + '/sources/{source_id}/preprocess')
        def send_to_preprocessing(source_id: str, user=Depends(auth)):
            with db() as conn:
                row = self.source_row(conn, source_id, user)
            content = h['read_stored_file'](row['storage_path'])
            # This explicit user action creates a separate preprocessing task.
            index = json.loads(row['diagnostics_json']).get('source_check', {}).get('spectrum_index')
            return h['_create_preprocessing_task'](content, row['source_name'], user, row['project_id'], confirm_conversion=True, spectrum_index=index)

        @app.post(route + '/saved-results')
        def save(payload: SaveResult, user=Depends(auth)):
            with self.lock, db() as conn:
                job = reader(conn, payload.job_id, user)
                if job['status'] != 'completed' or slug == 'ssnet' and job['kind'] != 'predict':
                    raise HTTPException(409, '仅可保存已完成的分析结果；训练模型在训练完成后自动保存。')
                old = conn.execute(f'SELECT * FROM {self.saved} WHERE job_id=?', (job['id'],)).fetchone()
                if old:
                    return dict(old)
                rid, stamp = uuid.uuid4().hex, now()
                conn.execute(f'INSERT INTO {self.saved} (id,user_id,job_id,title,created_at) VALUES (?,?,?,?,?)',
                             (rid, user['id'], job['id'], payload.title, stamp))
                return dict(id=rid, user_id=user['id'], job_id=job['id'], title=payload.title, created_at=stamp)

        @app.get(route + '/saved-results')
        def saved_results(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50), user=Depends(auth)):
            with db() as conn:
                total = conn.execute(f'SELECT COUNT(*) AS count FROM {self.saved} WHERE user_id=?', (user['id'],)).fetchone()['count']
                rows = conn.execute(f'SELECT * FROM {self.saved} WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?',
                                    (user['id'], page_size, (page - 1) * page_size)).fetchall()
                visible = []
                for row in rows:
                    try:
                        reader(conn, row['job_id'], user)
                        visible.append(dict(row))
                    except HTTPException:
                        continue
            return dict(items=visible, total=total, page=page, page_size=page_size)

        @app.get(route + '/saved-results/{result_id}')
        def saved_result(result_id: str, user=Depends(auth)):
            with db() as conn:
                saved = conn.execute(f'SELECT * FROM {self.saved} WHERE id=? AND user_id=?', (result_id, user['id'])).fetchone()
                if saved is None:
                    raise HTTPException(404, '已保存的分析不存在。')
                job = decoder(reader(conn, saved['job_id'], user))
            return dict(record=dict(saved), job=job)

    def source_row(self, conn, source_id, user):
        row = conn.execute(f'SELECT * FROM {self.sources} WHERE id=? AND user_id=?', (source_id, user['id'])).fetchone()
        if row is None:
            raise HTTPException(404, '本模块的光谱输入不存在。')
        if row['project_id']:
            self.h['get_project_row'](conn, row['project_id'], user)
        return row

    def decode_source(self, row):
        return dict(id=row['id'], source_name=row['source_name'], original=json.loads(row['original_json']),
                    diagnostics=json.loads(row['diagnostics_json']), created_at=row['created_at'], module=self.slug)

    def freeze(self, conn, source_id, user):
        row = self.source_row(conn, source_id, user)
        return dict(spectrum=json.loads(row['original_json']), steps=[], reference=dict(source_id=row['id'], module=self.slug),
                    metadata=json.loads(row['diagnostics_json']).get('source_check', {})), row['source_name'], row['project_id']

    def input(self, conn, payload, user):
        if payload.source_id:
            if payload.workflow_id or payload.version_id:
                raise HTTPException(400, '请选择本模块上传或预处理版本中的一个来源。')
            return self.freeze(conn, payload.source_id, user)
        if not payload.workflow_id:
            raise HTTPException(400, '请先选择光谱。')
        origin = conn.execute('SELECT module FROM ai_workflow_origins WHERE workflow_id=?', (payload.workflow_id,)).fetchone()
        if origin and origin['module'] != 'preprocessing':
            # Compatibility is limited to an existing input in this module.
            return self.freeze(conn, payload.workflow_id, user)
        return freeze_workflow_spectrum(conn, self.h, payload.workflow_id, payload.version_id, user)
