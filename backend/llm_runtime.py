"""Shared local inference budget; no prompts, credentials or spectra in logs."""
import threading
from contextlib import contextmanager

_LOCAL = threading.BoundedSemaphore(1)
AXIS_POLICY = '平台约定：未声明横轴单位时默认按拉曼位移 cm⁻¹ 处理，这是默认假定而非文件已声明。不要因未声明单位反复追问、拒绝生成方案或声称所有分析无效。历史对话中的单位追问不覆盖本约定。明确声明为波长、像素、能量或其他单位时不能直接当作拉曼位移，需遵守导入检查和转换要求。'


def axis_reference(value):
    """Apply the platform assumption to model evidence only, preserving raw metadata."""
    if isinstance(value, dict):
        result = {k: axis_reference(v) for k, v in value.items()}
        if 'axis_unit' in result:
            unit = str(result['axis_unit'] or '')
            if not unit.strip() or unit in ('未声明', '未知') or 'not declared' in unit:
                result['axis_unit'] = 'cm^-1 (platform default, not declared by file)'
                result['axis_unit_basis'] = 'platform_default'
        for key in ('warnings', 'import_warnings'):
            if isinstance(result.get(key), list):
                result[key] = ['文件未声明横轴单位，平台默认按拉曼位移 cm⁻¹ 处理。' if isinstance(w,str) and ('未声明轴单位' in w or '未声明横轴单位' in w) else w for w in result[key]]
        return result
    if isinstance(value, list):
        return [axis_reference(v) for v in value]
    return value


class ModelBusyError(RuntimeError):
    pass


@contextmanager
def inference_slot(settings):
    local = settings.get('provider') == 'ollama'
    acquired = not local or _LOCAL.acquire(timeout=15)
    if not acquired:
        raise ModelBusyError('本地模型正在处理其他请求，请稍后重试。')
    try:
        yield
    finally:
        if local:
            _LOCAL.release()


def compact_reference(value, depth=0):
    """Bound repeated page previews while retaining keys, units and scalar metrics."""
    if depth > 8:
        return '（更深层内容已省略）'
    if isinstance(value, dict):
        return {k: compact_reference(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        limit = 12 if value and isinstance(value[0], (list, tuple)) else 8
        if len(value) > limit:
            indexes = sorted(set(round(i * (len(value) - 1) / (limit - 1)) for i in range(limit)))
            return {'total_items': len(value), 'sampled_items': [compact_reference(value[i], depth + 1) for i in indexes], 'note': '均匀抽样，非完整数据'}
        return [compact_reference(v, depth + 1) for v in value]
    if isinstance(value, str) and len(value) > 700:
        return value[:700] + '（长文本已省略）'
    return value
