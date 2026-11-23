"""Versioned inference contract. Checkpoints and private overrides stay outside Git."""
import hashlib
import json
import os
import re
from pathlib import Path
from vib2mol_agent_package import ARCHIVE_SHA256, installed_agent

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REVISION = '732806b99abf4aedac07cf56ac34fd670948e338'
WEIGHTS_REVISION = '5c0a1aa60009ac9921e80da3e0019c8ec64abd58'
ARTIFACTS = {
    'generation': {'path': 'mols/raman-kekule_smiles/vib2mol/2025-07-10-07-46-68d484/epoch999.pth', 'sha256': '3c418ce5709eea6047f479b54b8f334d6a4eeeda31f7a7b82834b821c418f167'},
    'matching': {'path': 'mols/raman-kekule_smiles/vib2mol/2025-07-08-02-56-69bd7e/epoch999.pth', 'sha256': '75c6b17399f105dd9a7ab99c1d3f49f37d0b507ea54565dbdb1cb782d3516eee'},
}


def configuration(engine='official'):
    runtime = ROOT / '.runtime' / 'vib2mol'
    profile = dict(id='vib2mol-mols-raman-v1', engine='official', label='Vib2Mol 官方 Raman / MOLS',
                   source_revision=SOURCE_REVISION, weights_revision=WEIGHTS_REVISION,
                   start=400.0, end=4000.0, points=1024, normalization='positive_max',
                   formula_mode='post_filter', beam_size=10, max_tokens=128, temperature=3.5,
                   device='cpu', threads=1, generation_sha256=ARTIFACTS['generation']['sha256'],
                   matching_sha256=ARTIFACTS['matching']['sha256'])
    private = dict(python=str(ROOT / '.venv-vib2mol' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')),
                   source=str(runtime / 'source'), generation=str(runtime / 'generation.pth'), matching=str(runtime / 'matching.pth'))
    path = ROOT / 'backend' / 'structure_config.json'
    if path.exists():
        overrides = json.loads(path.read_text(encoding='utf-8-sig'))
        profile.update({k: v for k, v in overrides.get('profile', {}).items() if k in profile})
        private.update({k: str(v) for k, v in overrides.get('paths', {}).items() if k in private})
    # This adapter supports the one-channel architecture only. Other models need an adapter.
    if profile['formula_mode'] != 'post_filter' or profile['normalization'] != 'positive_max':
        raise ValueError('当前适配器仅支持单条 Raman、最大值归一化及生成后分子式筛选。')
    if not (profile['start'] < profile['end'] and profile['points'] == 1024):
        raise ValueError('模型波段或采样点配置无效。')
    if engine == 'agent':
        manifest = installed_agent(private['source'])
        profile.update(id=profile['id'] + '-agent-v1', engine='agent', label='Vib2Mol Agent · Raman 知识增强（实验）',
                       max_tokens=256, agent_archive_sha256=ARCHIVE_SHA256,
                       agent_package_sha256=manifest['package_sha256'] if manifest else None,
                       rag_profile='sdbs_raman', rag_weight=.35, rag_min_delta=.10,
                       rag_index='book_rag_index_v3_5.jsonl', planner='rule', llm_enabled=False)
    elif engine != 'official':
        raise ValueError('不支持的结构生成模式。')
    return profile, private


def public_configuration(engine='official'):
    profile, paths = configuration(engine)
    required = ['python', 'source', 'generation', 'matching']
    installed = all(Path(paths[key]).exists() for key in required)
    agent_ready = bool(installed_agent(paths['source']))
    ready = installed and (engine != 'agent' or agent_ready)
    return dict(profile=profile, ready=ready, default_engine='agent' if agent_ready else 'official',
                engines=[dict(id='official', label='Vib2Mol 原版', ready=installed),
                         dict(id='agent', label='Vib2Mol Agent · 知识增强（实验）', ready=installed and agent_ready)],
                message='' if ready else '请按 STRUCTURE_GENERATION.md 安装所选模型或 Agent 扩展。')


def formula_counts(value):
    if not value:
        return {}
    if len(value) > 120 or not re.fullmatch(r'(?:[A-Z][a-z]?[1-9]*[0-9]*)+', value):
        raise ValueError('分子式仅支持元素及正整数原子数，例如 C6H6。')
    elements = set('H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og'.split())
    counts = {}
    for element, count in re.findall(r'([A-Z][a-z]?)([0-9]*)', value):
        if element not in elements or (count and (count.startswith('0') or int(count) > 9999)):
            raise ValueError('分子式包含无效元素或原子数。')
        counts[element] = counts.get(element, 0) + int(count or 1)
    return counts


def prepare_spectrum(spectrum, profile):
    import numpy as np
    x = np.asarray(spectrum.get('wavenumber', []), dtype=float)
    y = np.asarray(spectrum.get('intensity', []), dtype=float)
    if x.ndim != 1 or y.ndim != 1 or len(x) != len(y) or not 8 <= len(x) <= 20000:
        raise ValueError('需要 8–20000 个点的一维波数、强度数据。')
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('光谱包含非有限数值。')
    differences = np.diff(x)
    reverse = bool(np.all(differences < 0))
    if not (reverse or np.all(differences > 0)):
        raise ValueError('波数必须严格单调且不能重复。')
    if reverse:
        x, y = x[::-1], y[::-1]
    start, end = profile['start'], profile['end']
    if x[0] > start or x[-1] < end:
        raise ValueError(f"当前模型需要完整覆盖 {start:g}–{end:g} cm⁻¹；此光谱仅覆盖 {x[0]:g}–{x[-1]:g} cm⁻¹，请使用完整波段数据。")
    grid = np.linspace(start, end, profile['points'])
    values = np.interp(grid, x, y)
    scale = float(values.max())
    if scale <= 0:
        raise ValueError('模型输入需要正的强度最大值，请检查光谱或基线校正结果。')
    warnings = ['官方模型以计算光谱为主训练，实验光谱的仪器差异与背景会影响结果；候选需要实验验证。']
    if np.any(values < 0):
        warnings.append('输入含负强度，已保留；请检查基线校正。')
    gaps = np.diff(x[(x >= start) & (x <= end)])
    if len(gaps) and gaps.max() > 20:
        warnings.append('波段内采样间距超过 20 cm⁻¹，插值不能恢复缺失的峰。')
    canonical = json.dumps(spectrum, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return dict(wavenumber=grid.tolist(), intensity=(values / scale).tolist(),
                preparation=dict(input_sha256=hashlib.sha256(canonical).hexdigest(),
                                 reversed=reverse, grid=[start, end, profile['points']],
                                 interpolation='linear_no_extrapolation', normalization='positive_max', scale=scale,
                                 original_points=len(x)), warnings=warnings)
