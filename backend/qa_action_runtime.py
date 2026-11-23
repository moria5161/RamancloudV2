"""Closed adapters to existing authenticated operations; never executes model code."""
import asyncio
import inspect
import io
import json
import time
import zipfile
import numpy as np
from fastapi import HTTPException, UploadFile, Response
from pydantic import ValidationError
from spectral_formats import standard_spectrum_content
from workflow_spectrum import freeze_workflow_spectrum
import ai_workflow as workflow


LABELS = dict(preprocess='智能光谱处理', hyperspectral='高光谱处理', library_match='库匹配',
    structure_generate='光谱到结构', ssnet_train='标准品模型训练', ssnet_predict='混合物解析',
    standardize='标准双列转换', split='拆分 Mapping', merge='合并光谱', convert='文本布局转换',
    export='导出结果', share='共享到项目')
MODULES = {
    'ai-analysis': ['preprocess', 'library_match', 'structure_generate', 'ssnet_predict', 'export', 'share'],
    'hyperspectral': ['hyperspectral', 'export', 'share'],
    'library-matching': ['library_match', 'preprocess', 'structure_generate', 'export', 'share'],
    'structure-generation': ['structure_generate', 'preprocess', 'library_match', 'export', 'share'],
    'spectral-unmixing': ['ssnet_train', 'ssnet_predict', 'preprocess', 'library_match', 'export', 'share'],
    'extra-tools': ['standardize', 'split', 'merge', 'convert'],
    'analysis-history': ['preprocess', 'library_match', 'structure_generate', 'ssnet_predict', 'export', 'share'],
    'projects': ['preprocess', 'library_match', 'structure_generate', 'export', 'share'],
}
PARAMS = {
    'preprocess': {'steps'}, 'hyperspectral': {'steps', 'preview_wavenumber'},
    'library_match': {'top_k', 'preprocessing_mode'},
    'structure_generate': {'engine', 'top_k', 'formula', 'rerank'},
    'ssnet_train': {'name','start','end','points','epochs','samples_per_epoch','batch_size','rf_samples','trees','device'},
    'ssnet_predict': set(), 'standardize': set(), 'split': {'instrument'}, 'merge': set(),
    'convert': {'conversion'}, 'export': {'format','original','processed'}, 'share': set(),
}
MODEL_OPS = {'library_match', 'structure_generate', 'ssnet_train', 'ssnet_predict'}


def invoke(app, path, method, user, **values):
    """Only server-written callers supply paths. Validate payloads as the original route does."""
    route = next((r for r in app.routes if getattr(r, 'path', '') == path and method in (getattr(r, 'methods', None) or [])), None)
    if route is None:
        raise HTTPException(503, '此功能接口尚未就绪。')
    signature = inspect.signature(route.endpoint)
    args = {}
    for name, param in signature.parameters.items():
        if name in ('user', 'current_user'):
            args[name] = user
        elif name in values:
            value = values[name]
            if inspect.isclass(param.annotation) and hasattr(param.annotation, 'parse_obj') and isinstance(value, dict):
                try:
                    value = param.annotation.parse_obj(value)
                except ValidationError:
                    raise HTTPException(400, '方案参数不符合该模块要求，请展开参数修改。')
            args[name] = value
        elif name == 'response':
            args[name] = Response()
        elif hasattr(param.default,'default'):
            args[name]=param.default.default
        elif param.default is inspect.Parameter.empty:
            raise HTTPException(400, '方案缺少必需输入：' + name)
    value = route.endpoint(**args)
    return asyncio.run(value) if inspect.isawaitable(value) else value


class ActionRuntime:
    def __init__(self, app, h):
        self.app, self.h = app, h

    def call(self, path, method, user, **values):
        return invoke(self.app, path, method, user, **values)

    def source(self, inputs, user):
        """Read immutable, owner/project checked sources. Client supplies IDs, never arrays or paths."""
        h = self.h
        ref = inputs.get('source') or {}
        if ref.get('reuse_job_id'):
            module=ref.get('module')
            if module not in ('library-matching','structure-generation','ssnet'):raise HTTPException(400,'来源模块无效。')
            job=self.call('/api/'+module+'/jobs/{job_id}','GET',user,job_id=ref['reuse_job_id'])
            source=job['input'].get('source') or (job['input'].get('sources') or [None])[0]
            if not source or 'spectrum' not in source:raise HTTPException(400,'该任务没有可复用的完整单谱输入。')
            project=None
            if module=='ssnet':project=next(iter(job['input'].get('projects',[])),None)
            else:
                with h['db_connect']() as conn:
                    table='library_match_jobs' if module=='library-matching' else 'structure_jobs'
                    project=conn.execute('SELECT project_id FROM '+table+' WHERE id=?',(job['id'],)).fetchone()['project_id']
            return dict(source,reference=ref),job.get('source_name') or job.get('name','已保存光谱'),project
        if ref.get('reference_id') is not None:
            value=self.call('/api/library-matching/references/{class_id}','GET',user,class_id=ref['reference_id'])
            return dict(spectrum={k:value[k] for k in ('wavenumber','intensity')},steps=[],reference=ref,metadata={'kind':'library_cache'}),value['name']+' · 库内验证输入',None
        if ref.get('file_index') == 0 and inputs.get('_files'):
            f=inputs['_files'][0]
            try:x,y,meta=h['_inspect_spectrum_upload'](h['read_stored_file'](f['path']),f['name'])
            except (ValueError,TypeError,OSError) as exc:raise HTTPException(400,'光谱附件无法用于处理：'+str(exc)[:200])
            if meta.get('selection_required'):raise HTTPException(400,'请先在模块中选择多谱文件的位置。')
            return dict(spectrum=dict(wavenumber=x.tolist(),intensity=y.tolist()),steps=[],reference=ref,metadata=meta),f['name'],inputs.get('project_id')
        if ref.get('workflow_id'):
            with h['db_connect']() as conn:
                vid=ref.get('version_id') or None
                if vid:
                    version=conn.execute('SELECT status FROM ai_plan_versions WHERE id=? AND workflow_id=?',(vid,ref['workflow_id'])).fetchone()
                    if version is None:raise HTTPException(404,'来源版本不存在。')
                    if version['status']!='completed':vid=None
                return freeze_workflow_spectrum(conn, h, ref['workflow_id'], vid, user)
        if ref.get('source_id'):
            module = ref.get('module')
            if module not in ('library-matching','structure-generation','ssnet'):
                raise HTTPException(400, '光谱来源模块无效。')
            value = self.call('/api/'+module+'/sources/{source_id}', 'GET', user, source_id=ref['source_id'])
            with h['db_connect']() as conn:
                prefix = {'library-matching':'library_match','structure-generation':'structure','ssnet':'ssnet'}[module]
                row = conn.execute('SELECT project_id FROM '+prefix+'_sources WHERE id=? AND user_id=?', (ref['source_id'],user['id'])).fetchone()
            return dict(spectrum=value['original'], steps=[], reference=ref, metadata=value['diagnostics'].get('source_check',{})), value['source_name'], row['project_id']
        if ref.get('run_id'):
            with h['db_connect']() as conn:
                run = h['row_to_analysis_run'](h['get_analysis_run_row'](conn, ref['run_id'], user))
            value = run['result']
            if not isinstance(value.get('intensity'), list):
                raise HTTPException(400, '当前结果没有完整单条光谱，不能作为此分析输入。')
            return dict(spectrum={k:value[k] for k in ('wavenumber','intensity')}, steps=run['steps'], reference=ref, metadata={}), run['source_name'], run['project_id']
        if ref.get('dataset_asset_id'):
            with h['db_connect']() as conn:
                row = conn.execute('SELECT * FROM data_assets WHERE id=?',(ref['dataset_asset_id'],)).fetchone()
                if row is None:raise HTTPException(404,'项目文件不存在。')
                h['get_project_row'](conn,row['project_id'],user)
            try:wave, intensity, meta = h['_inspect_spectrum_upload'](h['read_stored_file'](row['storage_path']), row['filename'])
            except (ValueError,TypeError,OSError) as exc:raise HTTPException(400,'项目文件无法用于单谱处理：'+str(exc)[:200])
            if meta.get('selection_required'):
                raise HTTPException(400, '请先选择原生多谱文件中的位置。')
            return dict(spectrum=dict(wavenumber=wave.tolist(),intensity=intensity.tolist()),steps=[],reference=ref,metadata=meta), row['filename'], row['project_id']
        raise HTTPException(400, '请先在模块中选择光谱，或在助手上传光谱后生成方案。')

    def check_inputs(self, inputs, user):
        """Rechecked at create/edit/execute/read and between every operation."""
        h = self.h
        with h['db_connect']() as conn:
            account = conn.execute('SELECT is_active FROM users WHERE id=?', (user['id'],)).fetchone()
            if account is None or not account['is_active']:
                raise HTTPException(403, '账号不可用。')
            if inputs.get('project_id'):
                h['get_project_row'](conn, inputs['project_id'], user)
            for rid in inputs.get('run_ids', []):
                h['get_analysis_run_row'](conn, rid, user)
            for aid in inputs.get('asset_ids',[]):
                asset=conn.execute('SELECT project_id FROM data_assets WHERE id=?',(aid,)).fetchone()
                if asset is None or asset['project_id']!=inputs.get('project_id'):raise HTTPException(404,'所选项目文件不存在。')
                h['get_project_row'](conn,asset['project_id'],user)
        if inputs.get('export_refs'):
            from spectrum_exports import SpectrumReference
            for ref in inputs['export_refs']:
                clean=strict_payload(SpectrumReference,ref)
                if clean.get('run_id'):
                    with h['db_connect']() as conn:h['get_analysis_run_row'](conn,clean['run_id'],user)
                else:
                    task=h['_qa_workflow']['detail'](clean['workflow_id'],user)
                    if clean.get('version_id') and not any(v['id']==clean['version_id'] for v in task['versions']):raise HTTPException(404,'导出版本不存在。')
        ref=inputs.get('source') or {}
        if ref.get('run_id'):
            with h['db_connect']() as conn:h['get_analysis_run_row'](conn,ref['run_id'],user)
        elif ref.get('dataset_asset_id'):
            with h['db_connect']() as conn:
                asset=conn.execute('SELECT project_id FROM data_assets WHERE id=?',(ref['dataset_asset_id'],)).fetchone()
                if asset is None:raise HTTPException(404,'项目文件不存在。')
                h['get_project_row'](conn,asset['project_id'],user)
        elif ref:self.source(inputs, user)
        if inputs.get('dataset_id'):
            h['cached_dataset'](inputs['dataset_id'], user)
        for ref in inputs.get('standards', []):
            self.source(dict(source=dict(ref, module=ref.get('module','ssnet'))), user)
        if inputs.get('model_id'):
            job = self.call('/api/ssnet/jobs/{job_id}', 'GET', user, job_id=inputs['model_id'])
            if job['kind'] != 'train' or job['status'] != 'completed':
                raise HTTPException(400, '请选择已完成的标准品模型。')
        if inputs.get('batch_id'):
            batch = self.call('/api/ai-workflow-batches/{bid}', 'GET', user, bid=inputs['batch_id'])
            ids = inputs.get('workflow_ids') or []
            available = {item['workflow_id'] for item in batch['items']}
            if not ids or len(ids)>100 or not set(ids).issubset(available):
                raise HTTPException(400, '请勾选当前批次中需要处理的光谱。')
            for wid in ids:
                h['_qa_workflow']['detail'](wid, user)

    def axis(self, inputs, user):
        if inputs.get('dataset_id'):
            return self.h['cached_dataset'](inputs['dataset_id'], user)['wavenumber']
        ref = inputs.get('source') or {}
        if inputs.get('_direct_preprocess') and ref.get('workflow_id'):
            # An edited workflow version replays its complete pipeline on the
            # original spectrum. Use the same axis as the execution engine.
            return self.source(dict(inputs, source={'workflow_id': ref['workflow_id']}), user)[0]['spectrum']['wavenumber']
        return self.source(inputs,user)[0]['spectrum']['wavenumber']

    def normalize_steps(self, steps, inputs, user, allowed, module=None):
        if not isinstance(steps,list) or not 1<=len(steps)<=5:
            raise HTTPException(400,'方案需要1～5个操作。')
        normalized, produced_spectrum, trained = [], False, False
        has_result=bool(inputs.get('run_ids') or (inputs.get('source') or {}).get('run_id'))
        for index, item in enumerate(steps):
            if not isinstance(item,dict) or set(item)-{'action','params'}:
                raise HTTPException(400,'方案结构无效。')
            action, params = item.get('action'), item.get('params',{})
            if action not in allowed or not isinstance(params,dict) or set(params)-PARAMS.get(action,set()):
                raise HTTPException(400,'包含未授权的操作或参数。')
            # An omitted setting keeps the value selected on the source page.
            # Explicit plan edits still take precedence; do not inherit settings
            # from a different module in a combined plan.
            settings=inputs.get('settings') or {}
            primary={'ai-analysis':'preprocess','hyperspectral':'hyperspectral',
                'library-matching':'library_match','structure-generation':'structure_generate',
                'spectral-unmixing':'ssnet_train' if settings.get('mode')=='train' or settings.get('name') else 'ssnet_predict',
                'extra-tools':settings.get('mode')}.get(module)
            if action==primary:
                params=dict({k:v for k,v in settings.items() if k in PARAMS[action]},**params)
            params = json.loads(json.dumps(params,allow_nan=False))
            if action in ('preprocess','hyperspectral'):
                has_result=True
                if index or produced_spectrum:
                    raise HTTPException(400,'光谱处理必须位于组合方案的第一步。')
                if action=='hyperspectral' and not inputs.get('dataset_id'):
                    raise HTTPException(400,'请先加载高光谱数据。')
                raw = params.get('steps',[])
                if action=='preprocess':
                    try:
                        params['steps'] = workflow.validate_steps(raw,self.axis(inputs,user))
                    except (ValueError,TypeError):
                        raise HTTPException(400,'处理步骤或参数未通过算法注册表校验。')
                    produced_spectrum=True
                else:
                    params['steps'] = hyper_steps(raw,self.axis(inputs,user))
                    data=self.h['cached_dataset'](inputs['dataset_id'],user)['data']
                    for step in params['steps']:
                        if step['method']=='tshi' and step['enabled']:
                            if data.ndim!=3:raise HTTPException(400,'TSHI只适用于成像数据，请改选适合时间序列的算法。')
                            size=step['params']['windowsize']
                            if size%2!=1 or size>min(data.shape[:2]):raise HTTPException(400,'TSHI窗口必须为不超过图像行列数的奇数。')
                    if params.get('preview_wavenumber') is not None and not min(self.axis(inputs,user))<=params['preview_wavenumber']<=max(self.axis(inputs,user)):
                        raise HTTPException(400,'成像波数超出数据范围。')
            elif action in MODEL_OPS:
                if action!='ssnet_train':has_result=True
                if inputs.get('dataset_id') or inputs.get('batch_id'):
                    raise HTTPException(400,'请先在模型模块选择一条光谱；不把数据立方体或整批文件当作单谱。')
                if action=='ssnet_train':
                    if not inputs.get('standards'):
                        raise HTTPException(400,'请先选择标准品光谱并填写目标名称。')
                    from ssnet import Training
                    params = strict_payload(Training,dict(params,standards=clean_refs(inputs['standards']),unit_confirmed=True))
                    params.pop('standards');params.pop('unit_confirmed');trained=True
                elif action=='ssnet_predict':
                    if not trained and not inputs.get('model_id'):
                        raise HTTPException(400,'请选择标准品模型，或先加入模型训练步骤。')
                    self.source(inputs,user)
                else:
                    if not produced_spectrum:self.source(inputs,user)
                    if action=='library_match':
                        from library_matching import MatchRequest
                        if 'preprocessing_mode' not in params:
                            source_steps=normalized[0]['params']['steps'] if produced_spectrum else self.source(inputs,user)[0].get('steps',[])
                            corrected=any(s.get('type') in ('baseline','baseline_correction') and s.get('enabled',True) and s.get('method')!='skip' for s in source_steps)
                            params['preprocessing_mode']='prepared' if corrected else 'auto'
                        params = strict_payload(MatchRequest,params)
                    else:
                        from structure_generation import GenerationRequest
                        params = strict_payload(GenerationRequest,params)
                    params = {k:v for k,v in params.items() if k in PARAMS[action]}
            elif action in ('standardize','split','merge','convert'):
                if not inputs.get('_files'):
                    raise HTTPException(400,'请先在附加工具或助手选择文件。')
                if action!='merge' and len(inputs['_files'])!=1:
                    raise HTTPException(400,'此操作一次需要一个文件。')
                if action=='convert' and params.get('conversion') not in ('horiba_to_nanophoton','nanophoton_to_horiba'):
                    raise HTTPException(400,'文本布局转换方向无效。')
                if action=='split' and params.get('instrument','auto') not in ('auto','horiba','nanophoton'):
                    raise HTTPException(400,'不支持的仪器布局。')
            elif action=='share':
                if not inputs.get('project_id'):
                    raise HTTPException(400,'请先选择目标项目。')
                if not has_result:
                    raise HTTPException(400,'请选择要共享的已完成记录。')
            elif action=='export':
                params = dict(format=params.get('format','txt'),original=params.get('original',False),processed=params.get('processed',True))
                if params['format'] not in ('txt','png','bundle') or not isinstance(params['original'],bool) or not isinstance(params['processed'],bool) or not (params['original'] or params['processed']):
                    raise HTTPException(400,'请选择TXT、PNG或完整结果包及原始/处理后数据。')
                if not index and not (inputs.get('run_ids') or inputs.get('source') or inputs.get('export_refs') or inputs.get('asset_ids')):
                    raise HTTPException(400,'请选择要导出的记录。')
                if inputs.get('asset_ids') and (params['format']!='bundle' or not params['original'] or params['processed']):raise HTTPException(400,'原始项目文件请选择完整原件包（bundle、原始数据）。')
            normalized.append(dict(action=action,params=params))
        if inputs.get('batch_id') and (len(steps)!=1 or steps[0]['action']!='preprocess'):
            raise HTTPException(400,'批量方案当前只允许批量预处理；后续模型分析需选择单条结果。')
        return normalized

    def forward_source(self, inputs, user, target, state):
        if state.get('workflow_id'):
            return dict(workflow_id=state['workflow_id'],version_id=state['version_id'])
        source,name,project=self.source(inputs,user)
        ref=source['reference']
        if ref.get('reuse_job_id') and ref.get('module')==target and target!='ssnet':return dict(reuse_job_id=ref['reuse_job_id'])
        if ref.get('reference_id') is not None and target=='library-matching':return dict(reference_id=ref['reference_id'])
        if ref.get('workflow_id'):return {k:ref[k] for k in ('workflow_id','version_id') if ref.get(k)}
        if ref.get('source_id') and ref.get('module')==target:return dict(source_id=ref['source_id'])
        # Explicit confirmed run imports a separate, owned source into the target module.
        file=UploadFile(filename='assistant_input.txt',file=io.BytesIO(standard_spectrum_content(source['spectrum']['wavenumber'],source['spectrum']['intensity'])))
        value=self.call('/api/'+target+'/sources/upload','POST',user,file=file,project_id=project,confirm_conversion=True,spectrum_index=None)
        return dict(source_id=value['id'])

    def preflight(self, inputs, steps, user):
        """Validate model installation and source constraints before queueing any mutation."""
        prior=False
        ref=inputs.get('source') or {}
        if ref.get('workflow_id') and ref.get('version_id'):
            task=self.h['_qa_workflow']['detail'](ref['workflow_id'],user)
            if any(v['id']==ref['version_id'] and v['status'] in ('running','queued','previewing') for v in task['versions']):
                raise HTTPException(409,'来源版本仍在执行，请等待完成。')
        for item in steps:
            a,p=item['action'],item['params']
            if a in ('preprocess','hyperspectral'):prior=True
            if a in ('library_match','structure_generate'):
                module='library-matching' if a=='library_match' else 'structure-generation'
                config=self.call('/api/'+module+'/config','GET',user)
                # Validate only when the current source belongs to the target module or workflow.
                ref=inputs.get('source') or {}
                if not prior and (ref.get('workflow_id') or ref.get('module')==module):
                    self.call('/api/'+module+'/validate','POST',user,payload=dict({k:v for k,v in ref.items() if k in ('workflow_id','version_id','source_id','reuse_job_id','reference_id')},**p,unit_confirmed=True))
                if a=='library_match' and config.get('ready') is False:
                    raise HTTPException(503,'库匹配模型尚未安装。')
                if a=='structure_generate':
                    from structure_profiles import public_configuration
                    if not public_configuration(p.get('engine','official'))['ready']:raise HTTPException(503,'结构生成模型尚未安装。')
            elif a.startswith('ssnet_'):
                if not self.call('/api/ssnet/config','GET',user)['ready']:raise HTTPException(503,'SSnet 模型环境未安装。')

    def execute_step(self, item, inputs, user, state, update, cancelled):
        a,p=item['action'],item['params'];h=self.h
        self.check_inputs(inputs,user)
        if a=='preprocess':
            ref=inputs.get('source') or {}
            if ref.get('workflow_id'):
                task=h['_qa_workflow']['detail'](ref['workflow_id'],user)
                wid=task['id'];parent=ref.get('version_id') or None
            else:
                source,name,project=self.source(inputs,user)
                if ref.get('run_id'):
                    with h['db_connect']() as conn:run=h['row_to_analysis_run'](h['get_analysis_run_row'](conn,ref['run_id'],user))
                    if run['analysis_type']=='spectrum' and isinstance(run['input'].get('intensity'),list):
                        source=dict(source,spectrum={k:run['input'][k] for k in ('wavenumber','intensity')})
                task=h['_create_preprocessing_task'](standard_spectrum_content(source['spectrum']['wavenumber'],source['spectrum']['intensity']),name,user,project,confirm_conversion=True)
                wid=task['id'];parent=None
            metadata=dict(qa_action_plan_id=state['plan_id'])
            if parent:
                with h['db_connect']() as conn:
                    old=h['_qa_workflow']['decode_version'](h['_qa_workflow']['version_row'](conn,wid,parent))
                metadata.update({k:v for k,v in old.get('metadata',{}).items() if k in ('phase','region')})
            planner=state.get('planner',{})
            provider=(planner.get('provider') or 'manual')+(':'+planner['model'][:40] if planner.get('model') else '')
            version=h['_qa_workflow']['new_version'](wid,user,state['goal'][:2000],p['steps'],parent,provider=provider,summary='AI 问答方案，经用户确认后运行。',metadata=metadata)
            state.update(workflow_id=wid,version_id=version['id'])
            if inputs.get('batch_id'):
                value=self.call('/api/ai-workflow-batches/{bid}/execute','POST',user,bid=inputs['batch_id'],payload=dict(template_workflow_id=wid,template_version_id=version['id'],workflow_ids=inputs['workflow_ids']))
                path,args='/api/ai-workflow-batches/{bid}',dict(bid=value['id']);url='/ai-analysis?batch='+value['id']
            else:
                self.call('/api/ai-workflows/{task_id}/versions/{vid}/execute','POST',user,task_id=wid,vid=version['id'],payload=None)
                path,args='/api/ai-workflows/{task_id}/versions/{vid}',dict(task_id=wid,vid=version['id']);url='/ai-analysis?task='+wid+'&version='+version['id']
            result=self.wait(path,args,user,update,cancelled,a,url)
            if inputs.get('batch_id'):
                if result.get('counts',{}).get('failed',0):raise HTTPException(409,'部分批量任务失败，请查看批次结果；不会继续后续操作。')
            elif result.get('analysis_run_id'):state['run_ids']=[result['analysis_run_id']]
            trace = result.get('trace', [])
            return dict(url=url,run_ids=state.get('run_ids',[]),result_summary=dict(
                batch=bool(inputs.get('batch_id')), completed_steps=sum(r.get('status') == 'done' for r in trace),
                status=result.get('status','completed'), processing_steps=[
                    dict(id=r['step']['id'], status=r['status']) for r in trace]))
        if a=='hyperspectral':
            source=h['cached_dataset'](inputs['dataset_id'],user)
            value=self.call('/api/process-hyperspectral','POST',user,payload=dict(wavenumber=[],dataset_id=inputs['dataset_id'],steps=[{k:v for k,v in s.items() if k in ('type','method','params')} for s in p['steps'] if s.get('enabled',True)],save_history=True,source_name=source['filename'],project_id=source.get('project_id'),preview_wavenumber=p.get('preview_wavenumber')))
            rid=value['data']['analysis_run']['id'];state['run_ids']=[rid]
            return dict(url='/analysis-history?run='+rid,run_ids=[rid],result_summary=dict(preview_wavenumber=value['data'].get('preview_wavenumber'),shape=value['data'].get('shape'),methods=[item.get('method',item.get('type')) for item in value['data'].get('history',[])]))
        if a in MODEL_OPS:
            if a=='ssnet_train':
                payload=dict(p,standards=clean_refs(inputs['standards']),unit_confirmed=True);module='ssnet';create='/api/ssnet/train'
            else:
                module={'library_match':'library-matching','structure_generate':'structure-generation','ssnet_predict':'ssnet'}[a]
                payload=dict(self.forward_source(inputs,user,module,state),**p,unit_confirmed=True)
                if a=='ssnet_predict':payload['model_id']=state.get('model_id') or inputs.get('model_id')
                create='/api/ssnet/predict' if a=='ssnet_predict' else '/api/'+module+'/jobs'
            value=self.call(create,'POST',user,payload=payload)
            url='/'+('spectral-unmixing' if module=='ssnet' else module)+'?job='+value['id']
            result=self.wait('/api/'+module+'/jobs/{job_id}',dict(job_id=value['id']),user,update,cancelled,a,url)
            if a=='ssnet_train':state['model_id']=result['id']
            elif result.get('analysis_run_id'):state['run_ids']=[result['analysis_run_id']]
            output=result.get('result',{})
            summary={k:output[k] for k in ('rf_score','model_name','duration_seconds','inference_performed') if k in output}
            if 'candidates' in output:summary['candidate_count']=len(output['candidates'])
            summary['warnings']=[str(w)[:200] for w in output.get('warnings',[])[:3]]
            return dict(url=url,run_ids=state.get('run_ids',[]),model_id=state.get('model_id'),result_summary=summary)
        if a in ('standardize','split','merge','convert'):
            files=[UploadFile(filename=f['name'],file=io.BytesIO(h['read_stored_file'](f['path']))) for f in inputs['_files']]
            values=dict(files=files) if a=='merge' else dict(file=files[0])
            response=self.call('/api/tools/'+a,'POST',user,**dict(values,**p))
            return dict(artifact=bytes(response.body),filename={'merge':'merged_mapping.txt','convert':'converted_mapping.txt'}.get(a,'spectra.zip'))
        rids=state.get('run_ids') or inputs.get('run_ids') or []
        if not rids and (inputs.get('source') or {}).get('run_id'):rids=[inputs['source']['run_id']]
        if a=='share':
            if not rids:raise HTTPException(400,'没有已完成的结果可共享。')
            for rid in rids:self.call('/api/analysis-runs/{rid}/warehouse','POST',user,rid=rid,payload=dict(project_id=inputs['project_id'],confirm_sharing=True))
            return dict(url='/projects?project='+inputs['project_id'],run_ids=rids)
        if a=='export':
            return self.export(inputs,user,state,rids,p)
        raise HTTPException(400,'不支持的操作。')

    def wait(self,path,args,user,update,cancelled,action,url):
        requested=False
        while True:
            value=self.call(path,'GET',user,**args)
            if 'active' in value:status='running' if value['active'] else 'completed'
            else:status=value['status']
            info = dict(status=status, progress=value.get('progress'), url=url, job_id=args.get('job_id'))
            if action == 'preprocess' and 'trace' in value:
                trace = [dict(id=record['step']['id'], status=record['status']) for record in value['trace']]
                if status == 'failed' and len(trace) < len(value.get('steps', [])):
                    trace.append(dict(id=value['steps'][len(trace)]['id'], status='failed'))
                info['result_summary'] = dict(processing_steps=trace)
            update(info)
            if cancelled() and not requested:
                if action in ('ssnet_train','ssnet_predict'):
                    self.call('/api/ssnet/jobs/{job_id}/cancel','POST',user,job_id=args['job_id'])
                elif 'bid' in args:self.call('/api/ai-workflow-batches/{bid}/cancel','POST',user,bid=args['bid'])
                requested=True
            if status not in ('queued','running','previewing'):
                if status!='completed':raise HTTPException(409,value.get('error') or '任务未完成。')
                return value
            time.sleep(.6)

    def export(self,inputs,user,state,rids,p):
        from spectrum_exports import SpectrumExportRequest
        # Result bundles support every analysis type. Single-spectrum TXT/PNG use the common authoritative exporter.
        output=io.BytesIO()
        if inputs.get('asset_ids'):
            response=self.call('/api/projects/{pid}/archive','GET',user,pid=inputs['project_id'],ids=','.join(inputs['asset_ids']))
            return dict(artifact=bytes(response.body),filename='project_original_files.zip')
        if p['format']=='bundle':
            if inputs.get('export_refs') and not state.get('run_ids'):
                rids=[]
                for ref in inputs['export_refs']:
                    if ref.get('run_id'):rids.append(ref['run_id']);continue
                    task=self.h['_qa_workflow']['detail'](ref['workflow_id'],user)
                    version=next((v for v in task['versions'] if v['id']==ref.get('version_id')),None) if ref.get('version_id') else next((v for v in reversed(task['versions']) if v['status']=='completed'),None)
                    if not version or version['status']!='completed' or not version.get('analysis_run_id'):raise HTTPException(400,'完整结果包需要已完成记录；未完成光谱请改选原始TXT或PNG。')
                    rids.append(version['analysis_run_id'])
            if not rids:raise HTTPException(400,'完整结果包需要已完成的分析记录。')
            with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
                for i,rid in enumerate(rids):
                    response=self.call('/api/analysis-runs/{rid}/resources/{kind}','GET',user,rid=rid,kind='bundle')
                    archive.writestr('%03d_result.zip'%i,bytes(response.body))
        else:
            refs=[dict(run_id=rid) for rid in state['run_ids']] if state.get('run_ids') else inputs.get('export_refs') or [dict(run_id=rid) for rid in rids]
            if not refs:
                ref=inputs.get('source') or {}
                refs=[{k:ref[k] for k in ('workflow_id','version_id','run_id') if ref.get(k)}]
            value=self.call('/api/spectra/export-data','POST',user,payload=dict(spectra=refs,original=p['original'],processed=p['processed']))
            if value['skipped']:raise HTTPException(400,'部分所选数据没有完整结果，请改选原始数据或完成处理后导出。')
            with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
                for i,item in enumerate(value['items']):
                    for role in ('original','processed'):
                        if role not in item:continue
                        spec=item[role]
                        if p['format']=='txt':content=standard_spectrum_content(spec['wavenumber'],spec['intensity'])
                        else:
                            from history_resources import figure
                            content=figure(self.h,dict(analysis_type='spectrum',input={},result=spec),'png')
                        archive.writestr('%03d_%s.%s'%(i,role,p['format']),content)
        if output.tell()>64*1024*1024:raise HTTPException(413,'导出包超过64MB，请缩小范围。')
        return dict(artifact=output.getvalue(),filename='analysis_export.zip')


def strict_payload(model, value):
    extra=set(value)-set(model.__fields__)
    if extra:raise HTTPException(400,'包含不支持的参数。')
    try:return model.parse_obj(value).dict()
    except ValidationError:raise HTTPException(400,'参数不符合当前模块要求。')


def clean_refs(refs):
    return [{k:v for k,v in ref.items() if k in ('source_id','workflow_id','version_id')} for ref in refs]


def hyper_registry():
    n=workflow.number
    return workflow.REGISTRY+[
        workflow.legacy_algorithms.METHODS['tsvd'],
        dict(type='denoise',method='tshi',label='TSHI 高光谱成像',params={
            'center_wavenumber':n(1000,-100000,100000,'中心波数'), 'half_width':n(20,2,128,'半波段宽度',True),
            'windowsize':n(5,3,31,'空间窗口',True),'count':n(100,1,1000,'迭代次数',True),
            'thr1':n(1e-5,0,1,'空间阈值'),'thr2':n(.3,-100,100,'光谱阈值'),
            'smoothness':dict(default='legacy',options=['legacy','variance'],label='平滑方式'),
            'bm3d_enabled':dict(default=False,boolean=True,label='BM3D'),'bm3d_sigma':n(5,0,1e6,'BM3D σ')})]


def hyper_steps(steps,wave):
    if not isinstance(steps,list) or not 1<=len(steps)<=10:raise HTTPException(400,'高光谱方案需要1～10个步骤。')
    out=[];wave=np.asarray(wave)
    for s in steps:
        if not isinstance(s,dict) or not isinstance(s.get('params',{}),dict) or not isinstance(s.get('enabled',True),bool):raise HTTPException(400,'高光谱步骤结构或启用状态无效。')
        spec=next((r for r in hyper_registry() if r['type']==s.get('type') and r['method']==s.get('method')),None)
        if spec is None or set(s.get('params',{}))-set(spec['params']):raise HTTPException(400,'高光谱算法或参数无效。')
        params={k:s.get('params',{}).get(k,v['default']) for k,v in spec['params'].items()}
        for k,v in params.items():
            rule=spec['params'][k]
            if v is None and rule.get('nullable'):continue
            if rule.get('boolean'):
                if not isinstance(v,bool):raise HTTPException(400,'布尔参数无效。')
            elif 'options' in rule:
                if v not in rule['options']:raise HTTPException(400,'选项参数无效。')
            elif isinstance(v,bool) or not isinstance(v,(int,float)) or not np.isfinite(v) or not rule['min']<=v<=rule['max'] or (rule['integer'] and v!=int(v)):
                raise HTTPException(400,'算法数值参数超出范围。')
        params={k:int(v) if v is not None and spec['params'][k].get('integer') else v for k,v in params.items()}
        if s.get('enabled',True):
            if s['method']=='tshi':
                if not min(wave)<=params['center_wavenumber']<=max(wave):raise HTTPException(400,'TSHI中心波数超出数据范围。')
                center=int(np.argmin(abs(wave-params['center_wavenumber'])));half=params['half_width']
                wave=wave[max(0,center-half):min(len(wave),center+half)]
            if s['method']=='cut':
                if not min(wave)<=params['start']<params['end']<=max(wave):raise HTTPException(400,'裁剪波段无效。')
                wave=wave[(wave>=params['start'])&(wave<=params['end'])]
            if len(wave)<3:raise HTTPException(400,'所选波段至少需要3个数据点。')
            if s['method']=='sg' and (params['window_size']%2!=1 or params['window_size']<=params['order'] or params['window_size']>len(wave)):raise HTTPException(400,'SG窗口必须为合法奇数，并小于当前处理波段点数。')
        out.append(dict(type=s['type'],method=s['method'],params=params,enabled=s.get('enabled',True),reason=str(s.get('reason',''))[:200]))
    try:workflow.validate_despike_order(out)
    except ValueError as exc:raise HTTPException(400,str(exc))
    return out
