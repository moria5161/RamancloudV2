"""Durable analysis arrays, human-readable exports and explicit warehouse entry."""
import csv
import io
import json
import uuid
import zipfile
import threading
import base64
from xml.sax.saxutils import escape
from typing import Optional

_RENDER_LOCK = threading.Lock()
LABELS = {'spectrum':'单光谱处理','hyperspectral':'高光谱处理','library_matching':'库匹配','structure_generation':'光谱到结构',
    'peak_fitting':'分峰拟合',
    'crop':'波段裁剪','cut':'波段裁剪','despike':'去鬼峰','denoise':'降噪','denoising':'降噪','baseline':'基线校正',
    'baseline_correction':'基线校正','sg':'SG 平滑','airpls':'airPLS','window_size':'窗口点数','poly_order':'多项式阶数',
    'lam':'平滑系数','threshold':'阈值','diff_order':'差分阶数','start':'起始波数','end':'终止波数','skip':'跳过',
    'name':'候选名称','formula':'分子式','smiles':'SMILES','model_score':'模型得分','matching_score':'匹配得分','generation_score':'生成得分'}

import numpy as np
from fastapi import Depends, HTTPException
from pydantic import BaseModel, constr
from hyperspectral_io import time_series_preview


class WarehouseRequest(BaseModel):
    project_id: str
    confirm_sharing: bool = False


class HistoryTitleRequest(BaseModel):
    title: constr(strip_whitespace=True, min_length=1, max_length=160)


def persist_arrays(h, conn, run_id, user, source, result):
    for role, key, payload in [('original', 'dataset_id', source), ('processed', 'processed_dataset_id', result)]:
        dataset = h['DATASETS'].get(payload.get(key))
        if dataset is None or conn.execute('SELECT run_id FROM analysis_array_files WHERE run_id=? AND role=?', (run_id, role)).fetchone():
            continue
        if dataset.get('owner_id') != user['id']:
            raise HTTPException(403, '数组不属于记录作者。')
        row = conn.execute('SELECT project_id FROM analysis_runs WHERE id=?', (run_id,)).fetchone()
        if row and dataset.get('project_id') and dataset['project_id'] != row['project_id']:
            raise HTTPException(403, '数组项目与记录不一致。')
        content = io.BytesIO()
        np.savez_compressed(content, wave=dataset['wavenumber'], data=dataset['data'],
                            mode=dataset['mode'], filename=dataset['filename'])
        location = h['store_project_file']('_analysis', run_id, role+'.npz', content.getvalue())
        conn.execute('INSERT INTO analysis_array_files (run_id,role,storage_path) VALUES (?,?,?)', (run_id, role, location))


def cached_array(h, run, role):
    section, key = (run['input'], 'dataset_id') if role == 'original' else (run['result'], 'processed_dataset_id')
    value = h['DATASETS'].get(section.get(key))
    if value is not None and value.get('owner_id') == run['user_id'] and value.get('project_id') in (None, run['project_id']):
        return value
    return None


def restore_arrays(h, run):
    with h['db_connect']() as conn:
        rows = conn.execute('SELECT * FROM analysis_array_files WHERE run_id=?', (run['id'],)).fetchall()
    for row in rows:
        section, key = (run['input'], 'dataset_id') if row['role'] == 'original' else (run['result'], 'processed_dataset_id')
        cached_id = section.get(key)
        if cached_id and cached_array(h, run, row['role']) is None:
            try:
                with np.load(io.BytesIO(h['read_stored_file'](row['storage_path'])), allow_pickle=False) as archive:
                    value = dict(wavenumber=archive['wave'], data=archive['data'],
                        mode=str(archive['mode']), filename=str(archive['filename']), owner_id=run['user_id'], project_id=run['project_id'])
                # Never overwrite a cache entry belonging to another run's scope.
                if cached_id in h['DATASETS']:
                    raise HTTPException(409, '缓存标识冲突，请重新加载数据。')
                h['DATASETS'][cached_id] = value
            except HTTPException as exc:
                if exc.status_code == 404:
                    raise HTTPException(409, '完整数组文件缺失，请重新加载源文件。') from exc
                raise
            except Exception as exc:
                raise HTTPException(409, '完整数组文件缺失或不可读取，请重新加载源文件。') from exc


def delete_artifacts(h, conn, rid):
    """Delete array references in caller's transaction; unlink returned paths AFTER commit."""
    rows = conn.execute('SELECT storage_path FROM analysis_array_files WHERE run_id=?', (rid,)).fetchall()
    conn.execute('DELETE FROM analysis_array_files WHERE run_id=?', (rid,))
    return [r['storage_path'] for r in rows]


def spectrum_csv(payload):
    wave = payload.get('wavenumber', [])
    values = payload.get('intensity', payload.get('mean_spectrum', []))
    if not len(wave) or len(wave) != len(values):
        raise HTTPException(409, '此记录没有可导出的完整光谱数值。')
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['RamanShift(cm^-1)', 'Intensity'])
    writer.writerows(zip(wave, values))
    return stream.getvalue().encode('utf-8-sig')


def result_file(h, run):
    if run['analysis_type'] == 'peak_fitting':
        from peak_fitting import parameter_csv
        return 'peak_parameters.csv', parameter_csv(run['result'])
    if run['analysis_type'] == 'hyperspectral':
        restore_arrays(h, run)
        dataset = cached_array(h, run, 'processed')
        if dataset is None:
            raise HTTPException(409, '旧记录的完整数据已过期，请重新加载源文件；预览不是完整数据。')
        from scipy.io import savemat
        stream = io.BytesIO()
        savemat(stream, dict(cube=dataset['data'], x=dataset['wavenumber'], mode=dataset['mode']))
        return 'processed.mat', stream.getvalue()
    if run['analysis_type'] in {'spectrum', 'mixture_analysis'}:
        return 'processed.csv', spectrum_csv(run['result'])
    candidates = run['result'].get('candidates', [])
    if not candidates:
        candidates = run['result'].get('result', {}).get('candidates', [])
    if not candidates:
        raise HTTPException(409, '此记录没有候选数据，请打开对应算法任务查看。')
    columns = ['rank', 'class_id', 'name', 'smiles', 'formula', 'inchikey', 'model_score', 'generation_score', 'matching_score']
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(candidates)
    return 'candidates.csv', stream.getvalue().encode('utf-8-sig')


def plot_values(h, run):
    if run['analysis_type'] == 'hyperspectral':
        restore_arrays(h, run)
        ds = cached_array(h, run, 'processed')
        if ds is None:
            raise HTTPException(409, '完整立方体未保存，不能生成结果图。')
        data = np.asarray(ds['data'])
        return ds['wavenumber'], data.mean(axis=tuple(range(data.ndim-1))), None
    result = run['result']
    if len(result.get('wavenumber', [])):
        return result['wavenumber'], result.get('intensity', result.get('mean_spectrum', [])), None
    candidates = result.get('candidates', [])
    if candidates:
        score_key = next((k for k in ('model_score','matching_score','generation_score') if candidates[0].get(k) is not None), None)
        if score_key:
            return [c.get('rank', i+1) for i,c in enumerate(candidates)], [c.get(score_key, float('nan')) for c in candidates], score_key
    raise HTTPException(409, '没有可用于结果图的数值。')


def figure(h, run, fmt):
    if run['analysis_type'] == 'peak_fitting':
        from peak_fitting import plot
        return plot(run['result'], fmt)
    wave, values, score = plot_values(h, run)
    try:
        with _RENDER_LOCK:
            import matplotlib
            matplotlib.use('Agg')
            from matplotlib import pyplot as plt
            fig = None
            try:
                is_hyper = run['analysis_type'] == 'hyperspectral'
                if is_hyper:
                    fig, (ax, image_ax) = plt.subplots(2, 1, figsize=(8, 8))
                    dataset = cached_array(h, run, 'processed')
                    data = np.asarray(dataset['data'])
                    wn = np.asarray(dataset['wavenumber'])
                    if data.ndim == 3:
                        target = run['result'].get('preview_wavenumber')
                        idx = int(np.abs(wn - (target if target is not None else (wn.min()+wn.max())/2)).argmin())
                        scale = max(1, int(np.ceil(max(data.shape[:2])/512)))
                        picture = image_ax.imshow(data[::scale,::scale,idx], cmap='viridis', aspect='auto')
                        image_ax.set(title='Processed image at %.4g cm^-1 (display sampled)' % wn[idx], xlabel='Column (sampled)', ylabel='Row (sampled)')
                    else:
                        scale = max(1, int(np.ceil(max(data.shape)/512)))
                        picture = image_ax.imshow(data[::scale,::scale], cmap='viridis', aspect='auto', extent=[wn[0],wn[-1],data.shape[0],0])
                        image_ax.set(title='Processed time series (display sampled)', xlabel='Raman shift (cm^-1)', ylabel='Acquisition index')
                    fig.colorbar(picture, ax=image_ax, label='Intensity')
                else:
                    fig, ax = plt.subplots(figsize=(8, 4.5))
                if score:
                    ax.bar(wave, values)
                    ax.set(xlabel='Candidate rank', ylabel=score, title='Model candidate scores (not identity confirmation)')
                else:
                    source = run['input']
                    raw_values = source.get('intensity', source.get('mean_spectrum', []))
                    if len(source.get('wavenumber', [])) == len(raw_values) and len(raw_values):
                        ax.plot(source['wavenumber'], raw_values, linewidth=.8, color='#cc8a25', label='Original')
                    ax.plot(wave, values, linewidth=0.85, color='#087f8c', label='Processed')
                    ax.legend()
                    ax.set(xlabel='Raman shift (cm^-1)', ylabel='Intensity (source units)', title='Spectrum comparison / spatial mean')
                ax.grid(alpha=0.2)
                fig.tight_layout()
                out = io.BytesIO()
                fig.savefig(out, format=fmt, dpi=160)
                return out.getvalue()
            finally:
                if fig is not None:
                    plt.close(fig)
    except ImportError as exc:
        raise HTTPException(503, '结果图需要 matplotlib。') from exc


def report_pdf(h, run):
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
        from reportlab.lib.styles import getSampleStyleSheet
    except ImportError as exc:
        raise HTTPException(503, 'PDF 报告需要 reportlab。') from exc
    with _RENDER_LOCK:
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = 'STSong-Light'
        style.wordWrap = 'CJK'
    story = []
    def text(value, style='Normal'):
        story.append(Paragraph(escape(str(value)).replace('\n','<br/>'), styles[style]))
        story.append(Spacer(1, 8))
    text('RamanCloud 分析报告', 'Title')
    text(run['title'], 'Heading2')
    for key, label in [('analysis_type','分析类型'),('source_name','来源文件'),('project_name','所属项目'),('created_at','保存时间')]:
        value = run.get(key) or '个人分析'
        text(label+'：'+str(LABELS.get(value, value)))
    text('参数与处理步骤', 'Heading2')
    for index, step in enumerate(run.get('steps', []), 1):
        method = step.get('method','')
        text(str(index)+'．'+LABELS.get(step.get('type'),step.get('type','处理步骤'))+' · '+LABELS.get(method,method), 'Heading3')
        text('已跳过' if step.get('enabled') is False or method == 'skip' else '已保存执行参数')
        for key, value in step.get('params', {}).items():
            if isinstance(value, (str,int,float,bool)) or value is None:
                text(LABELS.get(key,key)+'：'+str(value))
    if not run.get('steps'):
        text('此记录没有独立的预处理步骤。')
    text('结果图', 'Heading2')
    try:
        story.append(Image(io.BytesIO(figure(h, run, 'png')), width=460, height=460 if run['analysis_type']=='hyperspectral' else 259))
    except HTTPException as exc:
        text('结果图不可用：'+str(exc.detail))
    candidates = run['result'].get('candidates', [])
    for index, c in enumerate(candidates, 1):
        text('候选 '+str(c.get('rank',index)), 'Heading3')
        for key in ('name','formula','smiles','model_score','matching_score','generation_score'):
            if c.get(key) is not None:
                text(LABELS.get(key,key)+'：'+str(c[key]))
        if c.get('image_png') and len(c['image_png']) < 5_000_000:
            try:
                image = base64.b64decode(c['image_png'], validate=True)
                if image.startswith(b'\x89PNG\r\n\x1a\n'):
                    story.append(Image(io.BytesIO(image), width=230, height=140))
            except (ValueError, TypeError):
                text('结构图片不可读取。')
    text('候选及分数仅为保存的模型输出，不构成化学身份确认。完整精度数值见数据导出。原始数值重建文件与上传原始字节文件不同；预览不能恢复缺失的完整立方体。')
    out = io.BytesIO()
    SimpleDocTemplate(out, title=str(run['title']), author='RamanCloud').build(story)
    return out.getvalue()


def install_history_resources(app, h):
    db, auth = h['db_connect'], h['get_current_user']
    with db() as conn:
        conn.execute(f'''CREATE TABLE IF NOT EXISTS analysis_array_files (
            run_id {h['ID_SQL']} NOT NULL, role {h['SHORT_SQL']} NOT NULL,
            storage_path {h['PATH_SQL']} NOT NULL, PRIMARY KEY(run_id,role)
        ) {h['TABLE_OPTIONS']}''')

    def authorized(conn, rid, user):
        row = h['get_analysis_run_row'](conn, rid, user)
        run = h['row_to_analysis_run'](row)
        from model_history import enrich_model_history
        run = enrich_model_history(conn, run)
        return run

    @app.patch('/api/analysis-runs/{rid}')
    def rename_history(rid: str, payload: HistoryTitleRequest, user=Depends(auth)):
        with db() as conn:
            run = authorized(conn, rid, user)
            if run['user_id'] != user['id']:
                raise HTTPException(403, '仅作者可修改记录名称。')
            conn.execute('UPDATE analysis_runs SET title=?,updated_at=? WHERE id=?', (payload.title,h['iso_now'](),rid))
        return dict(title=payload.title)

    @app.get('/api/datasets/{did}/preview')
    def asset_preview(did: str, download: bool = False, user=Depends(auth)):
        with db() as conn:
            row = conn.execute('SELECT * FROM data_assets WHERE id=?', (did,)).fetchone()
            if row is None:
                raise HTTPException(404, '文件不存在。')
            h['get_project_row'](conn, row['project_id'], user)
        from spectral_formats import parse_dataset
        try:
            wave, values, metadata = parse_dataset(h['read_stored_file'](row['storage_path']), row['filename'])
        except (ValueError, KeyError) as exc:
            raise HTTPException(409, str(exc)) from exc
        data = np.asarray(values)
        if download:
            if data.ndim == 1 or (data.ndim == 2 and data.shape[0] == 1):
                response = h['attachment_response'](spectrum_csv(dict(wavenumber=np.asarray(wave).tolist(), intensity=data.reshape(-1).tolist())), 'standardized.csv', media_type='text/csv; charset=utf-8')
            else:
                from scipy.io import savemat
                stream = io.BytesIO()
                savemat(stream, dict(cube=data, x=np.asarray(wave)))
                response = h['attachment_response'](stream.getvalue(), 'standardized.mat')
            response.headers['Cache-Control'] = 'private, no-store'
            return response
        mean = data.reshape(-1, data.shape[-1]).mean(axis=0)
        indices = np.linspace(0, len(wave)-1, min(2000,len(wave)), dtype=int)
        result = dict(wavenumber=np.asarray(wave)[indices].tolist(), intensity=mean[indices].tolist(),
                      points=len(wave), shape=list(data.shape), metadata=metadata)
        if data.ndim == 3:
            scale = max(1,int(np.ceil(max(data.shape[:2])/96)))
            center = data.shape[-1]//2
            result.update(preview=data[::scale,::scale,center].tolist(), preview_wavenumber=float(wave[center]))
        from fastapi.responses import JSONResponse
        return JSONResponse(result, headers={'Cache-Control':'private, no-store'})

    @app.get('/api/projects/{pid}/archive')
    def warehouse_archive(pid: str, ids: str, user=Depends(auth)):
        selected = list(dict.fromkeys(ids.split(',')))
        if not 1 <= len(selected) <= 100 or any(not item or len(item)>64 for item in selected):
            raise HTTPException(400, '每次最多选择 100 个有效文件。')
        with db() as conn:
            h['get_project_row'](conn, pid, user)
            marks = ','.join('?' for _ in selected)
            rows = conn.execute('SELECT * FROM data_assets WHERE project_id=? AND id IN ('+marks+')', (pid,*selected)).fetchall()
        if len(rows) != len(selected):
            raise HTTPException(404, '选择的文件不存在或不属于当前项目。')
        if sum(row['file_size'] for row in rows) > 64*1024*1024:
            raise HTTPException(413, '本次打包超过 64 MB，请分批下载。')
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            total = 0
            for index,row in enumerate(rows,1):
                content = h['read_stored_file'](row['storage_path'])
                total += len(content)
                if total > 64*1024*1024:
                    raise HTTPException(413, '本次打包超过 64 MB，请分批下载。')
                name = h['clean_storage_name'](row['display_name'])+'_'+h['clean_storage_name'](row['filename'])
                archive.writestr(f'{index:03d}_'+name, content)
        response = h['attachment_response'](output.getvalue(), 'project_files.zip', 'application/zip')
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    def original(run):
        with db() as conn:
            asset = conn.execute('SELECT * FROM data_assets WHERE id=?', (run['source_dataset_id'],)).fetchone()
            if asset and asset['project_id'] == run['project_id']:
                return asset['filename'], h['read_stored_file'](asset['storage_path'])
            wid = run['result'].get('ai_workflow_id')
            task = conn.execute('SELECT * FROM ai_workflows WHERE id=? AND user_id=?', (wid, run['user_id'])).fetchone() if wid else None
            if task and task['storage_path']:
                return h['clean_storage_name'](task['source_name']), h['read_stored_file'](task['storage_path'])
        if run['analysis_type'] == 'hyperspectral':
            restore_arrays(h, run)
            dataset = cached_array(h, run, 'original')
            if dataset is None:
                raise HTTPException(409, '原始立方体未保存或已过期。')
            from scipy.io import savemat
            stream = io.BytesIO()
            savemat(stream, dict(cube=dataset['data'], x=dataset['wavenumber'], mode=dataset['mode']))
            return 'original_data.mat', stream.getvalue()
        return 'original_data.csv', spectrum_csv(run['input'])

    @app.get('/api/analysis-runs/{rid}/visualization')
    def visualization(rid: str, role: str = 'processed', wavenumber: Optional[float] = None,
                      x: Optional[int] = None, y: Optional[int] = None, user=Depends(auth)):
        with db() as conn:
            run = authorized(conn, rid, user)
        if role not in ('processed', 'original'):
            raise HTTPException(422, 'role 必须为 processed 或 original。')
        if (x is None) != (y is None) or (wavenumber is not None and not np.isfinite(wavenumber)):
            raise HTTPException(422, '坐标需同时提供；波数必须有限。')
        restore_arrays(h, run)
        dataset = cached_array(h, run, role)
        if dataset is None:
            raise HTTPException(409, '完整数组已过期或未保存；无法从预览恢复。')
        wave, cube = np.asarray(dataset['wavenumber']), np.asarray(dataset['data'])
        shape = run['input' if role == 'original' else 'result'].get('shape', [])
        if dataset.get('mode') == 'imaging' and cube.ndim == 2 and len(shape) == 3:
            if shape[-1] == len(wave) and int(np.prod(shape)) == cube.size:
                cube = cube.reshape(shape)
        if cube.ndim not in (2, 3) or cube.shape[-1] != len(wave) or not wave.size:
            raise HTTPException(409, '记录不包含有效的完整高光谱数组。')
        idx = int(np.abs(wave - (wavenumber if wavenumber is not None else (wave.min()+wave.max())/2)).argmin())
        scale = max(1, int(np.ceil(max(cube.shape[:2])/96)))
        def finite(values):
            a = np.asarray(values)
            return np.where(np.isfinite(a), a, None).tolist()
        if cube.ndim == 2:
            preview, preview_axis, indices = time_series_preview(wave, cube)
            output = dict(preview=finite(preview), preview_scale=1,
                          shape=list(cube.shape), mode='time_series',
                          preview_x=finite(preview_axis), preview_y=indices.tolist(),
                          mean_spectrum=dict(wavenumber=finite(wave), intensity=finite(cube.mean(axis=0))))
            from fastapi.responses import JSONResponse
            return JSONResponse(output, headers={'Cache-Control':'private, no-store'})
        output = dict(preview=finite(cube[::scale,::scale,idx]), preview_wavenumber=float(wave[idx]),
                      preview_scale=scale, shape=list(cube.shape), mode='imaging',
                      mean_spectrum=dict(wavenumber=finite(wave), intensity=finite(cube.mean(axis=(0,1)))))
        if x is not None:
            if not (0 <= x < cube.shape[1] and 0 <= y < cube.shape[0]):
                raise HTTPException(422, '坐标超出完整立方体范围。')
            output['pixel'] = dict(wavenumber=finite(wave), intensity=finite(cube[y,x,:]), x=x, y=y)
        from fastapi.responses import JSONResponse
        return JSONResponse(output, headers={'Cache-Control':'private, no-store'})

    @app.get('/api/analysis-runs/{rid}/resources/{kind}')
    def export(rid: str, kind: str, wavenumber: Optional[float] = None, user=Depends(auth)):
        with db() as conn:
            run = authorized(conn, rid, user)
        if wavenumber is not None:
            if not np.isfinite(wavenumber):
                raise HTTPException(422, '波数必须有限。')
            run['result'] = dict(run['result'], preview_wavenumber=wavenumber)
        if kind == 'json':
            name, content = 'analysis_result.json', json.dumps(run,ensure_ascii=False,allow_nan=False).encode('utf-8')
        elif kind == 'original':
            name, content = original(run)
        elif kind == 'data':
            name, content = result_file(h, run)
        elif kind == 'report':
            name, content = 'report.pdf', report_pdf(h, run)
        elif kind in ('figure', 'figure.svg', 'figure.png', 'png', 'svg'):
            fmt = 'png' if kind in ('figure.png', 'png') else 'svg'
            name, content = 'figure.'+fmt, figure(h, run, fmt)
        elif kind == 'curves' and run['analysis_type'] == 'peak_fitting':
            from peak_fitting import curve_text
            name, content = 'fit_curves.tsv', curve_text(run['result'])
        elif kind == 'bundle' and run['analysis_type'] == 'peak_fitting':
            from peak_fitting import bundle
            settings = next(s['params'] for s in run['steps'] if s['type'] == 'peak_fitting')
            name, content = 'peak_fit.zip', bundle(run['result'], settings, run['input']['source'])
        elif kind == 'bundle':
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                missing = []
                for folder, fn in [('original', original), ('processed', lambda r: result_file(h, r))]:
                    try:
                        filename, body = fn(run)
                        archive.writestr(folder+'/'+h['clean_storage_name'](filename), body)
                    except HTTPException as exc:
                        missing.append(str(exc.detail))
                for filename, producer in [('figure.png', lambda: figure(h, run, 'png')), ('figure.svg', lambda: figure(h, run, 'svg')), ('report.pdf', lambda: report_pdf(h, run))]:
                    try:
                        archive.writestr(filename, producer())
                    except HTTPException as exc:
                        missing.append(filename+': '+str(exc.detail))
                archive.writestr('process.json', json.dumps(dict(title=run['title'], steps=run['steps'], history=run['history']), ensure_ascii=False, indent=2))
                archive.writestr('README.txt', 'RamanCloud analysis export\n'+run['title']+'\n'+'\n'.join(missing))
            name, content = 'analysis_bundle.zip', output.getvalue()
        else:
            raise HTTPException(404, '不支持的文件类型。')
        media = {'pdf':'application/pdf', 'svg':'image/svg+xml', 'png':'image/png', 'zip':'application/zip', 'csv':'text/csv; charset=utf-8', 'json':'application/json; charset=utf-8', 'mat':'application/octet-stream'}.get(name.rsplit('.',1)[-1], 'application/octet-stream')
        response = h['attachment_response'](content, name, media_type=media)
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.post('/api/analysis-runs/{rid}/warehouse')
    def save_to_warehouse(rid: str, payload: WarehouseRequest, user=Depends(auth)):
        if not payload.confirm_sharing:
            raise HTTPException(400, '保存到项目将向成员共享原始数据、参数和结果，请先确认。')
        with db() as conn:
            # Serialize publication per target project before reading the run/link.
            h['get_project_row'](conn, payload.project_id, user)
            conn.execute('UPDATE projects SET updated_at=updated_at WHERE id=?', (payload.project_id,))
            conn.execute('UPDATE analysis_runs SET updated_at=updated_at WHERE id=? AND user_id=?', (rid,user['id']))
            run = authorized(conn, rid, user)
            if run['user_id'] != user['id']:
                raise HTTPException(403, '仅作者可将结果保存到仓库。')
            h['get_project_row'](conn, payload.project_id, user)
            if run['project_id'] and run['project_id'] != payload.project_id:
                raise HTTPException(400, '不能将结果移到其他项目。')
            conn.execute('UPDATE projects SET updated_at=updated_at WHERE id=?', (payload.project_id,))
            h['get_project_row'](conn, payload.project_id, user)
            existing = conn.execute('SELECT id FROM data_assets WHERE id=? AND project_id=?', (run['result_dataset_id'], payload.project_id)).fetchone()
            if existing:
                asset = conn.execute('SELECT data_kind FROM data_assets WHERE id=?', (existing['id'],)).fetchone()
                if asset['data_kind'] != 'processed':
                    raise HTTPException(409, '结果链接指向原始数据，请重新保存处理结果。')
                if not conn.execute('SELECT run_id FROM project_result_shares WHERE run_id=? AND project_id=?', (rid,payload.project_id)).fetchone():
                    conn.execute('INSERT INTO project_result_shares (run_id,project_id,shared_by,shared_at) VALUES (?,?,?,?)', (rid,payload.project_id,user['id'],h['iso_now']()))
                return dict(dataset_id=existing['id'])
            filename, content = result_file(h, run)
            did, now = uuid.uuid4().hex, h['iso_now']()
            location = h['store_project_file'](payload.project_id, did, filename, content)
            metadata = dict(analysis_run_id=rid, source_dataset_id=run['source_dataset_id'], source_name=run['source_name'],
                analysis_type=run['analysis_type'], provenance='platform', title=run['title'])
            conn.execute('''INSERT INTO data_assets (id,project_id,owner_id,filename,display_name,category,data_kind,data_type,
                instrument,mode,storage_path,file_size,metadata_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (did,payload.project_id,user['id'],filename,run['title'],'','processed',
                 'spectrum' if run['analysis_type'] in {'spectrum','mixture_analysis'} else 'mapping' if run['analysis_type']=='hyperspectral' else 'unknown',
                 None,None,location,len(content),json.dumps(metadata,ensure_ascii=False),now,now))
            conn.execute('UPDATE analysis_runs SET project_id=?,result_dataset_id=? WHERE id=?', (payload.project_id,did,rid))
            if not conn.execute('SELECT run_id FROM project_result_shares WHERE run_id=?', (rid,)).fetchone():
                conn.execute('INSERT INTO project_result_shares (run_id,project_id,shared_by,shared_at) VALUES (?,?,?,?)', (rid,payload.project_id,user['id'],now))
            # Never retag a personal cache entry also used by another private run.
            for role, section, key, column, version_type in [('original','input','dataset_id','input_json','original'), ('processed','result','processed_dataset_id','result_json','result')]:
                cached = cached_array(h, run, role)
                if cached is not None and cached.get('project_id') is None:
                    cloned_id = h['register_dataset'](cached['wavenumber'], cached['data'], cached['mode'], cached['filename'], user, payload.project_id)
                    saved = dict(run[section], **{key:cloned_id})
                    conn.execute('UPDATE analysis_runs SET '+column+'=? WHERE id=?', (json.dumps(saved,ensure_ascii=False),rid))
                    conn.execute('UPDATE analysis_versions SET payload_json=? WHERE run_id=? AND version_type=?', (json.dumps(saved,ensure_ascii=False),rid,version_type))
            h['project_event'](conn,payload.project_id,user,'warehouse_result',rid)
        return dict(dataset_id=did)

    @app.delete('/api/analysis-runs/{rid}/warehouse')
    def withdraw(rid: str, user=Depends(auth)):
        location = None
        with db() as conn:
            row = conn.execute('SELECT * FROM analysis_runs WHERE id=?', (rid,)).fetchone()
            if row is None or not row['project_id']:
                raise HTTPException(404, '仓库记录不存在。')
            project = h['get_project_row'](conn, row['project_id'], user)
            if row['user_id'] != user['id'] and project['my_role'] != 'admin':
                raise HTTPException(403, '仅作者或项目管理员可撤出仓库。')
            conn.execute('UPDATE projects SET updated_at=updated_at WHERE id=?', (row['project_id'],))
            conn.execute('UPDATE analysis_runs SET updated_at=updated_at WHERE id=?', (rid,))
            row = conn.execute('SELECT * FROM analysis_runs WHERE id=?', (rid,)).fetchone()
            did = row['result_dataset_id']
            if did:
                asset = conn.execute('SELECT * FROM data_assets WHERE id=? AND project_id=?', (did,row['project_id'])).fetchone()
                if asset:
                    if asset['data_kind'] != 'processed':
                        raise HTTPException(409, '此链接指向原始数据，不能作为处理后结果删除。')
                    referenced = (row['source_dataset_id'] == did or
                        conn.execute('SELECT id FROM analysis_runs WHERE id<>? AND (source_dataset_id=? OR result_dataset_id=?) LIMIT 1', (rid,did,did)).fetchone() or
                        conn.execute('SELECT id FROM ai_workflows WHERE source_dataset_id=? LIMIT 1', (did,)).fetchone())
                    conn.execute('UPDATE analysis_runs SET result_dataset_id=NULL WHERE id=?', (rid,))
                    if referenced:
                        # Withdrawal removes publication, not the inputs of derived work.
                        metadata = json.loads(asset['metadata_json'] or '{}')
                        other_share = conn.execute('''SELECT r.id FROM analysis_runs r JOIN project_result_shares s ON s.run_id=r.id
                            WHERE r.id<>? AND r.result_dataset_id=? LIMIT 1''', (rid,did)).fetchone()
                        metadata['withdrawn'] = not bool(other_share)
                        if other_share:
                            metadata['analysis_run_id'] = other_share['id']
                        conn.execute('UPDATE data_assets SET metadata_json=? WHERE id=?', (json.dumps(metadata,ensure_ascii=False),did))
                    else:
                        location = asset['storage_path']
                        conn.execute('DELETE FROM data_assets WHERE id=?', (did,))
                        if (conn.execute('SELECT id FROM data_assets WHERE storage_path=? LIMIT 1', (location,)).fetchone() or
                            conn.execute('SELECT id FROM ai_workflows WHERE storage_path=? LIMIT 1', (location,)).fetchone() or
                            conn.execute('SELECT run_id FROM analysis_array_files WHERE storage_path=? LIMIT 1', (location,)).fetchone()):
                            location = None
                else:
                    conn.execute('UPDATE analysis_runs SET result_dataset_id=NULL WHERE id=?', (rid,))
            conn.execute('DELETE FROM project_result_shares WHERE run_id=?', (rid,))
            h['project_event'](conn,row['project_id'],user,'withdraw_warehouse',rid)
        if location:
            h['remove_stored_file'](location)
        return dict(removed=True, analysis_run_id=rid)
