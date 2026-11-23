"""Read legacy model artifacts through the authorized frozen analysis record."""
import json


def ssnet_training_parameters(settings):
    keys = ('start', 'end', 'points', 'epochs', 'samples_per_epoch', 'batch_size', 'rf_samples', 'trees', 'device')
    return {key: settings[key] for key in keys if key in settings}


def enrich_mixture_history(conn, run):
    result = run['result']
    processing = dict(result.get('processing') or {})
    if result.get('job_id') and 'normalization_scale' not in processing:
        job = conn.execute("""SELECT input_json, result_json FROM ssnet_jobs
            WHERE id=? AND user_id=? AND kind='predict' AND status='completed'""",
            (result['job_id'], run['user_id'])).fetchone()
        if job and json.loads(job['result_json']).get('analysis_run_id') == run['id']:
            inputs = json.loads(job['input_json'])
            processing.update(grid=inputs['grid'], normalization_scale=inputs['prepared']['scale'])
    if result.get('model_id') and 'training_parameters' not in processing:
        model = conn.execute("""SELECT input_json FROM ssnet_jobs
            WHERE id=? AND user_id=? AND kind='train' AND status='completed'""",
            (result['model_id'], run['user_id'])).fetchone()
        if model:
            processing['training_parameters'] = ssnet_training_parameters(json.loads(model['input_json']).get('settings', {}))
    if processing:
        run['result'] = dict(result, processing=processing)
    return run


def enrich_model_history(conn, run):
    if run['analysis_type'] == 'mixture_analysis':
        return enrich_mixture_history(conn, run)
    tables = {'library_matching':'library_match_jobs','structure_generation':'structure_jobs'}
    table = tables.get(run['analysis_type'])
    if not table or not run['result'].get('job_id'):
        return run
    saved = run['result']
    if run['analysis_type'] == 'library_matching' and saved.get('model_input') is not None:
        return run
    if run['analysis_type'] == 'structure_generation' and all(candidate.get('image_png') for candidate in saved.get('candidates',[])):
        return run
    # Only this exact completed job can supply an old record's omitted plots.
    row = conn.execute(f'''SELECT result_json FROM {table} WHERE id=? AND user_id=?
        AND analysis_run_id=? AND status='completed' ''', (run['result']['job_id'],run['user_id'],run['id'])).fetchone()
    if not row:
        return run
    output = json.loads(row['result_json'])
    key = 'class_id' if run['analysis_type'] == 'library_matching' else 'id'
    originals = {candidate.get(key):candidate for candidate in output.get('candidates',[])}
    candidates = [{**originals.get(candidate.get(key),{}),**candidate} for candidate in saved.get('candidates',[])]
    for candidate in candidates:
        candidate.pop('sdf',None)
    run['result'] = {**output,**saved,'candidates':candidates}
    return run
