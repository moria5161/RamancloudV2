"""Persistent, owner-scoped peak-fitting jobs and reproducible exports."""
import csv
import io
import json
import logging
import threading
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from module_records import ModuleRecords
from peak_fitting_core import fit, prepare, voigt, IMPLEMENTATION


class StrictModel(BaseModel):
    class Config:
        extra = 'forbid'


class Peak(StrictModel):
    center: float
    center_min: float
    center_max: float
    width: float = Field(..., gt=0)
    width_min: float = Field(..., gt=0)
    width_max: float = Field(..., gt=0)
    area: Optional[float] = Field(None, gt=0)
    area_min: float = Field(0, ge=0)
    area_max: Optional[float] = Field(None, gt=0)
    eta: float = Field(.5, ge=0, le=1)
    eta_min: float = Field(0, ge=0, le=1)
    eta_max: float = Field(1, ge=0, le=1)
    shape: str = Field('voigt', regex='^(voigt|gaussian|lorentzian)$')


class FitRequest(StrictModel):
    source_id: Optional[str] = Field(None, max_length=64)
    workflow_id: Optional[str] = Field(None, max_length=64)
    version_id: Optional[str] = Field(None, max_length=64)
    reuse_job_id: Optional[str] = Field(None, max_length=64)
    unit_confirmed: bool = False
    baseline_confirmed: bool = False
    start: float
    end: float
    peaks: List[Peak] = Field(..., min_items=1, max_items=12)


def parameter_csv(result):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=['index', 'shape', 'center', 'area', 'height', 'width_parameter', 'fwhm', 'eta'], extrasaction='ignore')
    writer.writeheader(); writer.writerows(result['peaks'])
    return stream.getvalue().encode('utf-8-sig')


def curve_text(result):
    stream = io.StringIO(newline=''); writer = csv.writer(stream, delimiter='\t')
    writer.writerow(['RamanShift(cm^-1)', 'Observed', 'TotalFit', 'Residual'] + ['Peak_%s' % p['index'] for p in result['peaks']])
    writer.writerows(zip(result['wavenumber'], result['observed'], result['intensity'], result['residual'], *result['components']))
    return stream.getvalue().encode('utf-8')


def plot(result, fmt='png'):
    from history_resources import _RENDER_LOCK
    with _RENDER_LOCK:
        import matplotlib
        matplotlib.use('Agg')
        from matplotlib import pyplot as plt
        fig, (ax, residual_ax) = plt.subplots(2, 1, sharex=True, figsize=(9, 7), gridspec_kw={'height_ratios': [3, 1]})
        try:
            x = result['wavenumber']
            ax.plot(x, result['observed'], color='#64748b', label='Observed', lw=1)
            ax.plot(x, result['intensity'], color='#087e8b', label='Total fit', lw=1.6)
            for peak, values in zip(result['peaks'], result['components']):
                ax.plot(x, values, '--', label='Peak %s: %.4g' % (peak['index'], peak['center']), lw=1)
            ax.set(ylabel='Intensity (source units)', title='Peak fitting: R2=%.6g, RMSE=%.6g' % (result['r_squared'], result['rmse']))
            ax.legend(fontsize=8); ax.grid(alpha=.15)
            residual_ax.plot(x, result['residual'], color='#64748b', lw=1)
            residual_ax.axhline(0, color='#999999', lw=.8)
            residual_ax.set(xlabel='Raman shift (cm^-1)', ylabel='Residual'); residual_ax.grid(alpha=.15)
            fig.tight_layout(); output = io.BytesIO(); fig.savefig(output, format=fmt, dpi=180)
            return output.getvalue()
        finally:
            plt.close(fig)


def bundle(result, settings, source):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('peak_parameters.csv', parameter_csv(result))
        archive.writestr('curves.tsv', curve_text(result))
        archive.writestr('fit.png', plot(result))
        archive.writestr('settings.json', json.dumps(settings, ensure_ascii=False, allow_nan=False, indent=2))
        archive.writestr('source.json', json.dumps(source, ensure_ascii=False, allow_nan=False))
        archive.writestr('result.json', json.dumps(result, ensure_ascii=False, allow_nan=False))
        def two_columns(values):
            return ''.join('%.17g\t%.17g\n' % pair for pair in zip(result['wavenumber'], values))
        archive.writestr('total_fit.txt', two_columns(result['intensity']))
        archive.writestr('residual.txt', two_columns(result['residual']))
        for i, values in enumerate(result['components'], 1):
            archive.writestr('peak_%s.txt' % i, two_columns(values))
        archive.writestr('README.txt', 'RamanCloud peak fitting\nArea is the full analytic peak area (not the cropped integral).\nwidth_parameter follows the source script; fwhm is the actual full width at half maximum.\nNo baseline correction, normalization or interpolation is performed during fitting.\nPeak count and assignments are user hypotheses; fitting does not establish chemical identity.\n')
    return output.getvalue()


def install_peak_fitting(app, h):
    db, auth, now = h['db_connect'], h['get_current_user'], h['iso_now']
    encode = lambda v: json.dumps(v, ensure_ascii=False, allow_nan=False)
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='peak-fit')
    gate = threading.Lock()
    with db() as conn:
        conn.execute(f'''CREATE TABLE IF NOT EXISTS peak_fit_jobs (
            id {h['ID_SQL']} PRIMARY KEY, user_id {h['ID_SQL']} NOT NULL, project_id {h['ID_SQL']},
            source_name {h['NAME_SQL']} NOT NULL, status {h['SHORT_SQL']} NOT NULL,
            input_json {h['JSON_SQL']} NOT NULL, settings_json {h['JSON_SQL']} NOT NULL,
            result_json {h['JSON_SQL']} NOT NULL, error {h['JSON_SQL']} NOT NULL,
            analysis_run_id {h['ID_SQL']}, created_at {h['DATE_SQL']} NOT NULL, updated_at {h['DATE_SQL']} NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) {h['TABLE_OPTIONS']}''')
        h['create_index'](conn, 'idx_peak_fit_user', 'peak_fit_jobs', 'user_id,created_at')

    def reader(conn, jid, user):
        row = conn.execute('SELECT * FROM peak_fit_jobs WHERE id=? AND user_id=?', (jid, user['id'])).fetchone()
        if row is None:
            raise HTTPException(404, 'Peak-fitting job not found.')
        if row['project_id']:
            h['get_project_row'](conn, row['project_id'], user)
        return row

    def decode(row, detail=True):
        value = {key: row[key] for key in ('id', 'source_name', 'status', 'error', 'analysis_run_id', 'created_at', 'updated_at')}
        value['settings'] = json.loads(row['settings_json'])
        if detail:
            value.update(input=json.loads(row['input_json']), result=json.loads(row['result_json']))
        return value

    records = ModuleRecords(app, h, 'peak-fitting', 'peak_fit', reader, decode)

    @app.get('/api/peak-fitting/example')
    def example(user=Depends(auth)):
        import numpy as np
        x = np.linspace(2000., 2250., 501)
        guesses = [(2090., 60.), (2140., 25.), (2160., 38.)]
        truth = [(2090., 6000., 60., .35), (2140., 2200., 25., .5), (2160., 3500., 38., .65)]
        y = sum((voigt(x, *p) for p in truth), np.zeros_like(x))
        rows = [Peak(center=c, center_min=c-1, center_max=c+1, width=w, width_min=w*.9, width_max=w*1.1).dict() for c, w in guesses]
        return dict(simulated=True, spectrum=dict(wavenumber=x.tolist(), intensity=y.tolist()), settings=dict(start=2000, end=2250, peaks=rows))

    @app.on_event('startup')
    def recover():
        with db() as conn:
            conn.execute("UPDATE peak_fit_jobs SET status='failed',error=?,updated_at=? WHERE status IN ('queued','running')",
                         ('Service restarted. Please fit again.', now()))

    @app.on_event('shutdown')
    def shutdown():
        pool.shutdown(wait=False, cancel_futures=True)

    def validated(payload, user):
        if not payload.unit_confirmed:
            raise HTTPException(400, 'Confirm Raman shift in cm^-1 before fitting.')
        with db() as conn:
            if payload.reuse_job_id:
                if payload.source_id or payload.workflow_id or payload.version_id:
                    raise HTTPException(400, 'Choose exactly one spectrum source.')
                old = reader(conn, payload.reuse_job_id, user)
                source, name, project = json.loads(old['input_json'])['source'], old['source_name'], old['project_id']
            else:
                source, name, project = records.input(conn, payload, user)
        has_baseline = any(s.get('type') in ('baseline', 'baseline_correction') and s.get('enabled', True) and s.get('method') != 'skip' for s in source.get('steps', []))
        if not (has_baseline or payload.baseline_confirmed):
            raise HTTPException(400, 'Complete baseline correction or confirm that the uploaded spectrum is already corrected.')
        settings = payload.dict(include={'start', 'end', 'peaks', 'unit_confirmed', 'baseline_confirmed'})
        settings['baseline_evidence'] = 'saved_processing_steps' if has_baseline else 'user_confirmation'
        try:
            prepare(source['spectrum'], settings)
        except (TypeError, ValueError, OverflowError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return source, name, project, settings

    @app.post('/api/peak-fitting/validate')
    def validate(payload: FitRequest, user=Depends(auth)):
        source, name, _, settings = validated(payload, user)
        x, _, _, _, _, free = prepare(source['spectrum'], settings)
        return dict(source_name=name, points=len(x), free_parameters=int(free.sum()), implementation=IMPLEMENTATION)

    def worker(jid, user):
        try:
            with db() as conn:
                row = reader(conn, jid, user)
                conn.execute("UPDATE peak_fit_jobs SET status='running',updated_at=? WHERE id=?", (now(), jid))
            value = decode(row)
            result = fit(value['input']['source']['spectrum'], value['settings'])
            result['job_id'] = jid
            with db() as conn:
                reader(conn, jid, user)
            history = h['save_analysis_run'](current_user=user, analysis_type='peak_fitting', source_name=row['source_name'],
                steps=[dict(type='peak_fitting', method='voigt', params=value['settings'])], input_payload=value['input'],
                result_payload=result, history=[dict(implementation=IMPLEMENTATION, duration_seconds=result['duration_seconds'])],
                title=row['source_name'], project_id=row['project_id'], result_filename='peak_fitting.json')
            with db() as conn:
                conn.execute("UPDATE peak_fit_jobs SET status='completed',result_json=?,analysis_run_id=?,updated_at=? WHERE id=?",
                             (encode(result), history['id'], now(), jid))
        except Exception as exc:
            logging.getLogger(__name__).exception('Peak fit failed: %s', jid)
            message = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
            with db() as conn:
                conn.execute("UPDATE peak_fit_jobs SET status='failed',error=?,updated_at=? WHERE id=?", (message[:600], now(), jid))

    @app.post('/api/peak-fitting/jobs')
    def create(payload: FitRequest, user=Depends(auth)):
        source, name, project, settings = validated(payload, user)
        jid, stamp = uuid.uuid4().hex, now()
        with gate, db() as conn:
            count = conn.execute("SELECT COUNT(*) AS n FROM peak_fit_jobs WHERE status IN ('queued','running')").fetchone()['n']
            if count >= 12:
                raise HTTPException(429, 'The fitting queue is full. Please try again shortly.')
            snapshot = dict(source=source, **source['spectrum'])
            conn.execute('''INSERT INTO peak_fit_jobs (id,user_id,project_id,source_name,status,input_json,settings_json,result_json,error,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (jid, user['id'], project, name, 'queued', encode(snapshot), encode(settings), '{}', '', stamp, stamp))
        pool.submit(worker, jid, dict(user))
        with db() as conn:
            return decode(reader(conn, jid, user))

    @app.get('/api/peak-fitting/jobs')
    def jobs(user=Depends(auth)):
        with db() as conn:
            rows = conn.execute('SELECT id FROM peak_fit_jobs WHERE user_id=? ORDER BY created_at DESC LIMIT 100', (user['id'],)).fetchall()
            visible = []
            for row in rows:
                try:
                    visible.append(decode(reader(conn, row['id'], user), False))
                except HTTPException:
                    continue
            return visible

    @app.get('/api/peak-fitting/jobs/{jid}')
    def job(jid: str, user=Depends(auth)):
        with db() as conn:
            return decode(reader(conn, jid, user))

    @app.get('/api/peak-fitting/jobs/{jid}/download')
    def download(jid: str, kind: str = 'bundle', user=Depends(auth)):
        with db() as conn:
            value = decode(reader(conn, jid, user))
        if value['status'] != 'completed':
            raise HTTPException(409, 'The fit is not complete.')
        result = value['result']
        if kind == 'parameters': name, body, media = 'peak_parameters.csv', parameter_csv(result), 'text/csv; charset=utf-8'
        elif kind == 'curves': name, body, media = 'fit_curves.tsv', curve_text(result), 'text/tab-separated-values; charset=utf-8'
        elif kind == 'png': name, body, media = 'peak_fit.png', plot(result), 'image/png'
        elif kind == 'bundle': name, body, media = 'peak_fit.zip', bundle(result, value['settings'], value['input']['source']), 'application/zip'
        else: raise HTTPException(404, 'Unknown export format.')
        response = h['attachment_response'](body, name, media)
        response.headers['Cache-Control'] = 'private, no-store'
        return response
