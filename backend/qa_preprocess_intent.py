"""Translate an explicitly requested preprocessing plan into registered steps."""
import json
import re
import unicodedata
from typing import List, Optional

import numpy as np
from pydantic import BaseModel, Field, StrictBool

import ai_workflow as workflow
from compute_queue import ComputeCancelled
from llm_runtime import ModelBusyError
from workflow_review import checked_region, scoped_steps


TYPE_LABELS = {'cut': '波数裁剪', 'despike': '去鬼峰', 'denoise': '降噪', 'baseline': '基线校正'}
DEFAULT_METHODS = {'cut': 'cut', 'despike': 'despike', 'denoise': 'sg', 'baseline': 'airpls'}
PRESET_METHODS = {'despike': 'despike', 'denoise': 'f2p', 'baseline': 'airnet'}
ALGORITHM_NAMES = {
    'sg': r'sg|savitzky[– -]golay', 'wtd': r'wtd|小波|wavelet',
    'peer': 'peer', 'f2p': 'f2p|fast2peak', 'airnet': 'airnet',
    'airpls': 'airpls', 'aabs': 'aabs', 'imodpoly': 'imodpoly',
    'snip': 'snip', 'tsvd': 'tsvd', 'asls': 'asls',
}
METHOD_TYPES = {s['method']: s['type'] for s in workflow.REGISTRY} | {'tsvd': 'denoise', 'asls': 'baseline'}
METHOD = re.compile('|'.join(rf'(?P<{name}>(?<![a-z0-9_])(?:{pattern})(?![a-z0-9_]))'
                             for name, pattern in ALGORITHM_NAMES.items()))

OPERATIONS = {
    'cut': r'裁[剪切]|截取|保留\s*\d[^,;。]{0,32}(?:波段|波数|cm)|\b(?:crop|trim)\b',
    'despike': (r'(?:去(?:除|掉)?|移除|消除|剔除|清除)\s*(?:孤立的?)?(?:鬼峰|尖峰|尖刺|宇宙射线(?:干扰)?)'
                r'|(?:鬼峰|尖峰|尖刺|宇宙射线(?:干扰)?)(?:给我)?(?:去掉|去除|剔除|移除)'
                r'|\b(?:despik(?:e|ing)|remove\s+(?:the\s+)?(?:isolated\s+|cosmic[- ]ray\s+)?spikes)\b'),
    'denoise': (r'去噪|降(?:低|下)?(?:一点|一下)?噪(?:声)?|平滑|减噪|(?:压低|减小|减弱|减少)(?:谱线的?)?(?:高频)?噪声'
                r'|(?:细小|细碎|高频)的?(?:抖动|波动)(?:能|可以)?(?:压一压|减小|压低)'
                r'|\b(?:denois(?:e|ing)|smooth(?:ing)?|reduce\s+(?:the\s+)?(?:high[- ]frequency\s+)?noise)\b'),
    'baseline': (r'基线[校矫]正|[校矫]正基线|校准基线|背景(?:扣除|[校矫]正)'
                 r'|(?:扣|去)(?:除|掉)?(?:缓慢(?:起伏|变化)的?|慢变的?)?(?:基线|背景)'
                 r'|(?:基线|(?:缓慢(?:起伏|变化)的?|慢变的?)?(?:背景|底))扣掉'
                 r'|(?:缓慢(?:起伏|变化)的?|慢变的?)(?:底|背景)(?:去掉|去除)'
                 r'|\b(?:baseline\s+correction|correct\s+(?:the\s+)?baseline|subtract\s+(?:the\s+)?background)\b'),
}
OPERATION = re.compile('|'.join(f'(?P<{kind}>{phrases})' for kind, phrases in OPERATIONS.items()))
SENTENCES = re.compile(r'[。!?;\n]+|(?<!\d)\.|\.(?!\d)')
CLAUSES = re.compile(r',|然后|接着|最后|而是|但是?|(?<!别)(?<!不)再(?!生)|\b(?:and then|then|but|instead)\b')
QUESTION = re.compile(
    r'为什么|为何|怎么(?!样)|如何|什么意思|是什么意思|是什么|(?:什么|有何)(?:区别|影响|用处|作用|差别|原理)'
    r'|(?:什么|哪[个种])(?:样的?)?(?:算法|方法)|区别(?:在哪|是什么)|效果怎么样|哪个好|哪[个种].{0,12}(?:更好|更合适)'
    r'|要不要|是否(?:有必要|需要)|有必要吗|需不需要|(?:推荐|建议).{0,20}(?:吗|哪|什么)'
    r'|讲讲|讲解|解读|介绍一下|介绍.{0,18}(?:方法|算法|原理)|(?:帮我)?解释|(?:对比|比较).{0,18}(?:算法|方法|区别)'
    r'|\b(?:what|why|how|explain|describe|difference between|should i|which (?:method|algorithm))\b')
REFERENCE = re.compile(
    r'^(?:如果|假如|例如|比如|假设|关于)|(?:已经|刚刚|刚才|之前|昨天|已)(?:做[过了]|完成了?|执行了|进行了|处理过)'
    r'|(?:去噪|降噪|平滑|基线[校矫]正|去鬼峰)(?:以?后|之前|了吗|过了吗|了没有|的结果)'
    r'|[“「"].+[”」"]\s*(?:这句|这句话|这个词|的意思|是指)'
    r'|\b(?:already|for example|if i|after i|i (?:have )?(?:denoised|smoothed))\b')
CHAT_ONLY = re.compile(r'(?:你好|您好|谢谢|好的?|可以|行|是的|收到|明白了?|嗯+|ok(?:ay)?|hi|hello|thanks|yes)[\s。!?.]*')
SKIP = re.compile(r'不要|(?<!分)(?<!个)别|不用|不(?:必|需要|做|用|再)|无需|跳过|省略|除了|免去|关闭|取消'
                  r'|\b(?:don.t|do not|no|without|skip|except|omit)\b')
SKIP_SUFFIX = re.compile(r'^\s*(?:这[一步个项]*\s*)?(?:不要|别做|不用|不做|跳过|先不做|保持不变)|^\s+(?:off|unchanged)\b')
KEEP_BASELINE = re.compile(r'(?:别(?:碰|动|改)|不(?:动|改|处理|做)|保留|跳过)(?:光谱的)?基线(?:[校矫]正)?'
                           r'|基线(?:[校矫]正)?(?:别动|保持原样|保持不变)|\b(?:leave|keep)\s+(?:the\s+)?baseline\s+(?:alone|unchanged)\b')
REVISION = re.compile(r'(?:刚才|上一[次轮版]|现有|原来)(?:的)?[^。!?]{0,32}(?:换|改|调整|去掉|删掉|取消|加上|补上)'
                      r'|(?:其他|其余)(?:步骤|参数)?(?:都)?(?:保持)?(?:不变|保留)|(?:上[一个]版|之前的方案)|\b(?:rest unchanged|instead|previous plan)\b')
EDIT = re.compile(r'换成|换用|改成|改为|改用|换到|设为|设成|设到|调整|删掉|关闭|取消|补上|加上'
                  r'|\b(?:switch|change|disable|enable|set)\b')
PICK_METHOD = re.compile(r'(?:使用|选用|采用|换用|改用|换成|改成|改为|用|选)\s*$|\b(?:use|with|switch to|change to)\s*$')
EXCLUSIVE = re.compile(r'(?:只|仅)(?:做|要|需要|保留|用)?\s*$|\b(?:only|just)\s*$')
NUMBER = r'[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:e[+-]?\d+)?'
RANGE = re.compile(rf'({NUMBER})\s*(?:[-–—~]|到|至|\bto\b)\s*({NUMBER})(?![.\d])')
PARAMETER_NAMES = {
    'window_size': r'(?:窗口(?:大小|长度|宽度)?|window(?: size)?|window_size)',
    'order': r'(?:拟合阶数|多项式阶数|poly(?:nomial)? order)',
    'lam': r'(?:lambda|λ|lam|平滑系数)',
    'diff_order': r'(?:差分阶数|diff_order)',
    'threshold': r'(?:检测阈值|threshold)',
    'fwhm_threshold': r'(?:半高宽阈值|fwhm_threshold)',
    'level': r'(?:分解层数|小波层数|level)',
}
VALUE_SEPARATOR = r'\s*(?:(?:调|改|设(?:置)?)(?:到|成|为)|[:=]|为|用|取|of)?\s*'
PARAMETERS = {
    name: re.compile(rf'(?<![a-z_]){alias}{VALUE_SEPARATOR}({NUMBER})')
    for name, alias in PARAMETER_NAMES.items()
}
MODEL_CONSTRAINT = re.compile(r'参数|阈值|阶数|窗口|层数|系数|带宽|更强|更弱|轻一点|柔和|温柔'
                              r'|\b(?:parameter|threshold|order|window|level|coefficient|stronger|gentler)\b')
UNMAPPED_ACTION = re.compile(r'减弱|压低|压下去|压一压|减小|消除|去掉|移除|扣掉|滤掉|抑制|处理一下'
                             r'|\b(?:remove|reduce|subtract|filter|attenuate|suppress)\b')
PARAMETER_FOLLOWUP = '请明确要修改的算法或参数值。'
CONFLICT = '同一处理步骤有冲突，请说明希望采用哪一种设置。'
STEPS_REQUIRED = '请说明要做的处理，例如去鬼峰、降噪或校正基线。'
STEP_TO_KEEP = '请说明本次希望保留哪一步处理。'


class Change(BaseModel):
    type: str = Field(..., regex='^(cut|despike|denoise|baseline)$')
    method: Optional[str] = Field(None, max_length=24)
    enabled: StrictBool = True
    params: dict = Field(default_factory=dict)
    evidence: str = Field('', max_length=150)

    class Config:
        extra = 'forbid'


class Intent(BaseModel):
    kind: str = Field(..., regex='^(plan|revise|clarification)$')
    changes: List[Change] = Field(default_factory=list, max_items=4)
    clarification: str = Field('', max_length=450)

    class Config:
        extra = 'forbid'


def normalized(message):
    return unicodedata.normalize('NFKC', message).casefold().strip()


def read_parameters(clause, kind, method):
    if kind == 'cut' and (limits := RANGE.search(clause)):
        return dict(zip(('start', 'end'), map(float, limits.groups())))
    spec = next((s for s in workflow.REGISTRY if s['method'] == method), {})
    params = {}
    for name in spec.get('params', {}):
        if name in PARAMETERS and (value := PARAMETERS[name].search(clause)):
            params[name] = float(value[1])
    return params


def read_clause(clause, selected):
    matches = list(OPERATION.finditer(clause))
    choices = [m for m in METHOD.finditer(clause)
               if PICK_METHOD.search(clause[:m.start()]) and not SKIP.search(clause[:m.start()])]
    # A named method can identify a step, e.g. “换成小波” or “用 AirPLS 处理”.
    if not matches and len(choices) == 1:
        matches = choices
    changes = []
    negative = False
    exclusive = False
    for index, match in enumerate(matches):
        kind = METHOD_TYPES[match.lastgroup] if match.re is METHOD else match.lastgroup
        start = matches[index - 1].end() if index else 0
        end = matches[index + 1].start() if index + 1 < len(matches) else len(clause)
        before, after = clause[start:match.start()], clause[match.end():end]
        exclusive |= bool(EXCLUSIVE.search(before))
        negative |= bool(SKIP.search(before) or re.search(r'(?:不|未)\s*$', before))
        skipped = negative or bool(SKIP_SUFFIX.match(after))
        method = None
        if match.re is METHOD:
            method = match.lastgroup
        elif len(matches) == 1 and len(choices) == 1:
            method = choices[0].lastgroup
        elif choices:
            # Multiple operations can name their own method in one conjunction.
            methods = [m.lastgroup for m in choices if start <= m.start() < end and METHOD_TYPES[m.lastgroup] == kind]
            if len(set(methods)) == 1:
                method = methods[0]
        candidate = method or selected.get(kind) or DEFAULT_METHODS[kind]
        params = read_parameters(clause, kind, candidate) if not skipped and len(matches) == 1 else {}
        changes.append(Change(type=kind, method=method, enabled=not skipped, params=params, evidence=match[0]))
    if KEEP_BASELINE.search(clause) and not any(change.type == 'baseline' for change in changes):
        changes.append(Change(type='baseline', enabled=False, evidence=KEEP_BASELINE.search(clause)[0]))
    return changes, exclusive


def preset_intent():
    return Intent(kind='plan', changes=[Change(type=kind, method=method) for kind, method in PRESET_METHODS.items()])


SYSTEM = '''用户已经选择“生成预处理方案”。只提取这次需要的光谱预处理步骤和明确给出的设置，返回 JSON {kind,changes,clarification}。
kind=plan：新方案，可同时有一个或多个步骤。kind=revise：修改已有方案，只列改动。kind=clarification：没有明确处理步骤或要求相冲突时问一个具体问题。
changes 每项为 {type,method,enabled,params,evidence}。操作类型：cut=保留指定波数区间；despike=去孤立异常尖点或宇宙射线；denoise=减少细碎波纹、噪声；baseline=扣除缓慢变化的背景。保留用户的明确步骤，跳过某步用 enabled=false。不要添加未请求的步骤。
known_changes 是从这轮识别出的明确指令。补充其中缺失的内容，不能覆盖明确的类型和排除项。evidence 逐字引用当前消息中支撑该操作或参数的一段原话。method 和 params 仅提取用户指定的值，否则填 null 和 {}。
例：“能把短周期的纹路压下去，再把慢慢抬高的底扣掉吗”→ plan，仅 denoise、baseline。“不做背景扣除，换个小波去噪”→ revise（已有方案时），baseline=false、denoise=wtd。
历史只用来解释这轮的明确引用。已经过去的指令不能用于重新生成方案。'''

INTENT_SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['kind', 'changes', 'clarification'],
    'properties': {
        'kind': {'type': 'string', 'enum': ['plan', 'revise', 'clarification']},
        'clarification': {'type': 'string'},
        'changes': {'type': 'array', 'maxItems': 4, 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['type', 'method', 'enabled', 'params', 'evidence'],
            'properties': {
                'type': {'type': 'string', 'enum': list(TYPE_LABELS)},
                'method': {'type': ['string', 'null']}, 'enabled': {'type': 'boolean'},
                'params': {'type': 'object'}, 'evidence': {'type': 'string'},
            },
        }},
    },
}


def read_commands(message, selected):
    """Resolve explicit clauses before asking the model about free-form language."""
    changes = {}
    unresolved = []
    action_clauses = []
    exclusive = False
    for sentence in SENTENCES.split(message):
        sentence = sentence.strip()
        if not sentence:
            continue
        if re.search(r'(?:这[几个些两三四步项种个]+|它们|这些步骤)(?:的|分别)?(?:是指|指什么|有什么|是什么|怎么|如何)', sentence):
            continue
        for part in CLAUSES.split(sentence):
            clause = part.strip()
            if not clause:
                continue
            if QUESTION.search(clause) or REFERENCE.search(clause):
                continue
            if CHAT_ONLY.fullmatch(clause):
                continue
            action_clauses.append(clause)
            clause_changes, only = read_clause(clause, selected)
            exclusive |= only
            if not clause_changes and MODEL_CONSTRAINT.search(clause) and changes:
                param_changes = []
                for step in changes.values():
                    if step.enabled:
                        method = step.method or selected.get(step.type) or DEFAULT_METHODS[step.type]
                        params = read_parameters(clause, step.type, method)
                        if params:
                            param_changes.append(step.copy(update={'params': params}))
                if len(param_changes) == 1:
                    clause_changes = param_changes
            for change in clause_changes:
                old = changes.get(change.type)
                if old:
                    if (old.enabled != change.enabled or old.method and change.method and old.method != change.method
                            or any(key in old.params and old.params[key] != value for key, value in change.params.items())):
                        raise ValueError(CONFLICT)
                    change = change.copy(update={'evidence': old.evidence,
                                                 'method': change.method or old.method,
                                                 'params': {**old.params, **change.params}})
                changes[change.type] = change
            if MODEL_CONSTRAINT.search(clause) and not any(change.params or not change.enabled for change in clause_changes):
                unresolved.append(clause)
            elif not clause_changes and (UNMAPPED_ACTION.search(clause) or EDIT.search(clause)):
                if not REVISION.search(clause):
                    unresolved.append(clause)
    return changes, action_clauses, unresolved, exclusive


def model_intent(message, history, settings, previous, changes):
    existing = [{k: step[k] for k in ('type', 'method', 'params', 'enabled') if k in step}
                for step in (previous or [])[:10] if isinstance(step, dict)]
    request = dict(message=message, history=[dict(role=m['role'], content=m['content'][:800]) for m in history[-6:]],
                   current_plan=existing, known_changes=[change.dict() for change in changes.values()],
                   algorithms=[dict(type=s['type'], method=s['method'], params=list(s['params'])) for s in workflow.REGISTRY])
    try:
        raw = workflow.call_chat_completion(settings, [dict(role='system', content=SYSTEM), dict(
            role='user', content=json.dumps(request, ensure_ascii=False))], json_mode=True, max_tokens=850, timeout=30,
            output_schema=INTENT_SCHEMA if settings.get('provider') == 'ollama' else None)
        return Intent.parse_raw(raw)
    except (ComputeCancelled, ModelBusyError):
        raise
    except Exception:
        return None


def supported_model_changes(intent, action_clauses, known, exclusive):
    result = {}
    resolved = set()
    if not intent or intent.kind == 'clarification':
        return result, resolved
    for change in intent.changes:
        evidence = normalized(change.evidence)
        clause = next((part for part in action_clauses if evidence and evidence in part), '')
        if not clause:
            continue
        explicit, _ = read_clause(clause, {})
        types = {step.type for step in explicit}
        if change.type not in types:
            if exclusive or change.type in known or types:
                continue
            if SKIP.search(clause) and change.enabled:
                continue
            if change.type == 'despike' and not re.search(r'鬼峰|尖刺|尖[峰点]|宇宙射线|spike|cosmic', evidence):
                continue
        method = normalized(change.method or '')
        if method and method not in clause and not any(m.lastgroup == method for m in METHOD.finditer(clause)):
            method = ''
        numbers = {float(value) for value in re.findall(NUMBER, clause)}
        params = {key: value for key, value in change.params.items()
                  if (isinstance(value, (int, float)) and not isinstance(value, bool) and value in numbers)
                  or (isinstance(value, str) and value and normalized(value) in clause)}
        change = change.copy(update={'method': method or None, 'params': params})
        if not MODEL_CONSTRAINT.search(clause) or change.params:
            resolved.add(clause)
        if change.type in result and (change.method, change.enabled, change.params) != (
                result[change.type].method, result[change.type].enabled, result[change.type].params):
            raise ValueError(CONFLICT)
        result[change.type] = change
    return result, resolved


def interpret_preprocessing(message, history, settings, previous=None, displayed=None):
    text = normalized(message)
    current = previous or displayed or []
    selected = {step.get('type'): step.get('method') for step in current if isinstance(step, dict)}
    if len(history) >= 2 and history[-2]['role'] == 'user' and history[-1]['role'] == 'assistant':
        asked_range = re.match(r'请提供要保留的起止波数|give the start and end wavenumbers', normalized(history[-1]['content']))
        if asked_range and (limits := RANGE.match(text)):
            if re.fullmatch(r'\s*(?:cm(?:\^-?1|-1)?\s*)?[。.!]?', text[limits.end():]):
                message = f"{history[-2]['content']}。裁剪范围为 {text}"
                text = normalized(message)
    try:
        known, clauses, unresolved, exclusive = read_commands(text, selected)
        enabled = any(change.enabled for change in known.values())
        revision = bool(REVISION.search(text) or previous and (EDIT.search(text) or known and not enabled))
        if not clauses:
            return Intent(kind='clarification', clarification=STEPS_REQUIRED), True
        if known and not unresolved:
            if not enabled and not revision:
                return Intent(kind='clarification', clarification=STEP_TO_KEEP), True
            if exclusive and revision:
                for kind in selected.keys() - known.keys():
                    if kind in TYPE_LABELS:
                        known[kind] = Change(type=kind, enabled=False)
            return Intent(kind='revise' if revision else 'plan', changes=list(known.values())), True

        inferred = model_intent(message, history, settings, current, known)
        semantic, resolved = supported_model_changes(inferred, clauses, known, exclusive)
        if pending := set(unresolved) - resolved:
            clarification = PARAMETER_FOLLOWUP if any(MODEL_CONSTRAINT.search(clause) for clause in pending) else (
                '请具体说明希望如何处理这部分光谱。')
            return Intent(kind='clarification', clarification=clarification), False
        for kind, change in known.items():
            suggestion = semantic.pop(kind, None)
            if change.enabled and suggestion and suggestion.enabled:
                change = change.copy(update={'method': change.method or suggestion.method,
                                             'params': {**suggestion.params, **change.params}})
            known[kind] = change
        if known or semantic:
            revision |= bool(previous and inferred and inferred.kind == 'revise')
            changes = sorted((known | semantic).values(), key=lambda c: text.index(normalized(c.evidence)))
            if not revision and not any(change.enabled for change in changes):
                return Intent(kind='clarification', clarification=STEP_TO_KEEP), False
            return Intent(kind='revise' if revision else 'plan', changes=changes), False
        return Intent(kind='clarification', clarification=(inferred.clarification if inferred else '') or STEPS_REQUIRED), False
    except ValueError as exc:
        return Intent(kind='clarification', clarification=str(exc)), True


def compile_steps(intent, message, wave, displayed, previous, region, *, preset=False):
    """Resolve defaults and check the complete requested pipeline against the real axis."""
    if len({change.type for change in intent.changes}) != len(intent.changes):
        raise ValueError(CONFLICT)
    current = {s['type']: s for s in displayed if isinstance(s, dict) and s.get('type') in TYPE_LABELS}
    existing = previous or list(current.values())
    if intent.kind == 'revise' and not existing:
        raise ValueError('当前没有可修改的方案，请描述这次要执行的处理。')
    steps = {s['type']: s for s in existing if s.get('enabled', True)} if intent.kind == 'revise' else {}
    registry = {(s['type'], s['method']): s for s in workflow.REGISTRY}
    available = {(s['type'], s['method']) for s in workflow.available_registry()}
    for change in intent.changes:
        kind = change.type
        if not change.enabled:
            steps.pop(kind, None)
            continue
        inherited = steps.get(kind) or current.get(kind) or {}
        method = change.method
        params_requested = change.params
        if kind == 'cut' and not {'start', 'end'} <= set(params_requested):
            raise ValueError('请提供要保留的起止波数，例如 800–1500 cm⁻¹。')
        if method is None:
            preferred = PRESET_METHODS.get(kind)
            inherited_method = inherited.get('method')
            candidates = (inherited_method, preferred) if intent.kind == 'revise' else (preferred, inherited_method)
            method = next((candidate for candidate in (*candidates, DEFAULT_METHODS[kind])
                           if (kind, candidate) in available and params_requested.keys() <= registry[kind, candidate]['params'].keys()),
                          None)
            if method is None:
                if params_requested:
                    raise ValueError('算法参数不受支持。')
                method = DEFAULT_METHODS[kind]
        if (kind, method) not in registry:
            raise ValueError('指定的算法不适用于这一步，请从本站算法目录选择。')
        if (kind, method) not in available:
            if preset:
                _, reason = workflow.legacy_algorithms.availability(registry[kind, method])
                raise ValueError(f'{registry[kind, method]["label"]}：{reason}')
            raise ValueError('当前算法环境未就绪，请检查所选算法或明确选择其他算法。')
        params = dict(inherited.get('params', {})) if inherited.get('method') == method and kind != 'cut' else {}
        params.update(params_requested)
        steps[kind] = dict(type=kind, method=method, params=params, enabled=True, reason='按本次处理要求生成。')
    processing = list(steps.values())
    if region and 'cut' not in steps and not any(c.type == 'cut' for c in intent.changes):
        processing = scoped_steps(processing, checked_region(region, wave), wave)
    if not processing:
        raise ValueError('当前要求没有保留任何处理步骤，请说明希望执行哪一步。')
    if intent.kind == 'revise':
        # A new crop belongs before the algorithms; preserve all other steps.
        processing.sort(key=lambda step: step['type'] != 'cut')
    elif not re.search(r'再|然后|接着|最后|\b(?:first|then|before|after)\b', message, re.I):
        processing.sort(key=lambda step: list(TYPE_LABELS).index(step['type']))
    return workflow.validate_steps(processing, np.asarray(wave, dtype=float))
