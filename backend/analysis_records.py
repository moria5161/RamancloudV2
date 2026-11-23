"""Read-only summaries of resumable work, alongside existing immutable analysis results."""
import json
from fastapi import Depends, HTTPException


def install_analysis_records(app, h):
    @app.get('/api/analysis-records/tasks')
    def pending_records(user=Depends(h['get_current_user'])):
        items, batches = [], []
        with h['db_connect']() as conn:
            rows = conn.execute('''SELECT w.*,v.id AS version_id,v.status AS version_status,v.error AS version_error
                FROM ai_workflows w JOIN ai_workflow_origins o ON o.workflow_id=w.id
                LEFT JOIN ai_plan_versions v ON v.id=(SELECT p.id FROM ai_plan_versions p
                    WHERE p.workflow_id=w.id ORDER BY p.created_at DESC,p.id DESC LIMIT 1)
                WHERE w.user_id=? AND o.module='preprocessing' ORDER BY w.updated_at DESC''', (user['id'],)).fetchall()
            for row in rows:
                if row['project_id']:
                    try:
                        h['get_project_row'](conn, row['project_id'], user)
                    except HTTPException:
                        continue
                batch = conn.execute('''SELECT b.id,b.name FROM ai_batch_items i JOIN ai_workflow_batches b ON b.id=i.batch_id
                    WHERE i.workflow_id=? AND b.user_id=?''', (row['id'], user['id'])).fetchone()
                preview = dict(ai_workflow_id=row['id'])
                if row['version_status'] == 'completed':
                    existing = conn.execute('SELECT r.id FROM analysis_runs r JOIN ai_plan_versions v ON v.analysis_run_id=r.id WHERE v.id=?', (row['version_id'],)).fetchone()
                    if existing or not batch:
                        continue
                    saved = conn.execute('SELECT trace_json FROM ai_plan_versions WHERE id=?', (row['version_id'],)).fetchone()
                    trace = json.loads(saved['trace_json'])
                    final = trace[-1].get('after', {}) if trace else {}
                    wave, values = final.get('wavenumber', []), final.get('intensity', [])
                    if wave and len(wave) == len(values):
                        n = min(60, len(wave))
                        indices = [int(i * (len(wave) - 1) / max(1, n - 1)) for i in range(n)]
                        preview.update(wavenumber=[wave[i] for i in indices], intensity=[values[i] for i in indices])
                items.append(dict(id='workflow:' + row['id'], kind='workflow', status=row['version_status'] or 'draft',
                    title=row['source_name'], source_name=row['source_name'], analysis_type='spectrum', project_id=row['project_id'],
                    created_at=row['created_at'], updated_at=row['updated_at'], workflow_id=row['id'], version_id=row['version_id'],
                    batch_id=batch['id'] if batch else None, batch_name=batch['name'] if batch else None,
                    result_available=row['version_status'] == 'completed',
                    error=row['version_error'] or '', result=preview))
            for slug, records in h.get('_analysis_module_records', {}).items():
                rows = conn.execute(f'SELECT id FROM {records.prefix}_jobs WHERE user_id=? ORDER BY created_at DESC', (user['id'],)).fetchall()
                for row in rows:
                    try:
                        source_row = records.reader(conn, row['id'], user)
                        job = records.decoder(source_row, detail=False)
                    except HTTPException:
                        continue
                    if slug == 'ssnet' and job['kind'] != 'predict':
                        continue
                    # Completed jobs already have one analysis result. Old SSnet
                    # jobs remain openable without silently migrating user data.
                    if job['status'] == 'completed' and (slug != 'ssnet' or job.get('analysis_run_id')):
                        continue
                    items.append(dict(id=slug + ':' + job['id'], kind='module', module=slug,
                        job_id=job['id'], status=job['status'], title=job.get('name') or job.get('source_name'),
                        source_name=job.get('source_name') or job.get('name'), created_at=job['created_at'],
                        updated_at=job['updated_at'], error=job.get('error', ''),
                        project_id=dict(source_row).get('project_id'),
                        analysis_type={'ssnet':'mixture_analysis','library-matching':'library_matching','structure-generation':'structure_generation','peak-fitting':'peak_fitting'}[slug]))
            rows = conn.execute('SELECT * FROM ai_workflow_batches WHERE user_id=? ORDER BY updated_at DESC', (user['id'],)).fetchall()
            for row in rows:
                projects = conn.execute('''SELECT DISTINCT w.project_id FROM ai_batch_items i JOIN ai_workflows w ON w.id=i.workflow_id
                    WHERE i.batch_id=? AND w.project_id IS NOT NULL''', (row['id'],)).fetchall()
                allowed = True
                for project in projects:
                    try:
                        h['get_project_row'](conn, project['project_id'], user)
                    except HTTPException:
                        allowed = False
                        break
                if not allowed:
                    continue
                invalid = conn.execute("SELECT id,relative_path,error FROM ai_batch_items WHERE batch_id=? AND workflow_id IS NULL AND status<>'deleted' ORDER BY position", (row['id'],)).fetchall()
                for member in invalid:
                    items.append(dict(id='batch-item:' + member['id'], kind='batch_item', item_id=member['id'],
                        batch_id=row['id'], batch_name=row['name'], title=member['relative_path'], source_name=member['relative_path'],
                        analysis_type='spectrum', status='invalid', error=member['error'], project_id=projects[0]['project_id'] if len(projects) == 1 else None,
                        created_at=row['created_at'], updated_at=row['updated_at']))
                # A member may also be processed from its own page. The record
                # summary follows that latest workflow state, not stale batch counters.
                members = conn.execute('''SELECT i.status,v.status AS latest_status
                    FROM ai_batch_items i LEFT JOIN ai_plan_versions v ON v.id=(
                        SELECT p.id FROM ai_plan_versions p WHERE p.workflow_id=i.workflow_id
                        ORDER BY p.created_at DESC,p.id DESC LIMIT 1) WHERE i.batch_id=?''', (row['id'],)).fetchall()
                counts = {}
                for member in members:
                    status = member['latest_status'] or member['status']
                    if status in ('draft', 'preview'):
                        status = 'ready'
                    counts[status] = counts.get(status, 0) + 1
                batches.append(dict(id=row['id'], name=row['name'], created_at=row['created_at'], updated_at=row['updated_at'],
                    project_id=projects[0]['project_id'] if len(projects) == 1 else None, counts=counts, total=sum(counts.values())))
        return dict(items=items, batches=batches)
