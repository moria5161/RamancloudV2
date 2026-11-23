"""Validation and normalization for AI-generated RamanCloud commands."""

import math
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Tuple
from legacy_algorithms import METHODS


DENOISE_ALIASES = {
    'f2p':'f2p',
    'fast2peak':'f2p',
    "sg": "sg",
    "sg filter": "sg",
    "sg denoise": "sg",
    "sg滤波": "sg",
    "savitzky-golay": "sg",
    "savitzky golay": "sg",
    "savitzky golay filter": "sg",
    "savitzky_golay": "sg",
    "sgolay": "sg",
    "wtd": "wtd",
    "wavelet": "wtd",
    "wavelet denoising": "wtd",
    "wavelet denoise": "wtd",
    "小波": "wtd",
    "小波去噪": "wtd",
    "peer": "peer",
    "peer denoise": "peer",
    "peer去噪": "peer",
    "tsvd": "tsvd",
    "truncated svd": "tsvd",
    "svd": "tsvd",
    "截断奇异值": "tsvd",
    "截断奇异值分解": "tsvd",
}

BASELINE_ALIASES = {
    'airnet':'airnet',
    "airpls": "airpls",
    "air pls": "airpls",
    "airpls_old": "airpls_old",
    "airpls legacy": "airpls_old",
    "aspls": "aspls",
    "as pls": "aspls",
    "aabs": "aabs",
    "auto-adaptive": "aabs",
    "auto adaptive": "aabs",
    "自适应": "aabs",
    "自适应基线": "aabs",
    "imodpoly": "imodpoly",
    "imod poly": "imodpoly",
    "penalizedpoly": "penalizedpoly",
    "penalized poly": "penalizedpoly",
    "snip": "snip",
    "rollingball": "rollingball",
    "rolling ball": "rollingball",
    "滚动球": "rollingball",
    "mormol": "mormol",
    "irsqr": "irsqr",
}

ACTION_ALIASES = {
    "process": "process_spectrum",
    "process spectrum": "process_spectrum",
    "process_spectrum": "process_spectrum",
    "process hyperspectral": "process_hyperspectral",
    "process_hyperspectral": "process_hyperspectral",
    "process cube": "process_hyperspectral",
    "process dataset": "process_hyperspectral",
    "apply": "process_spectrum",
    "run": "process_spectrum",
    "run pipeline": "process_spectrum",
    "运行": "process_spectrum",
    "处理": "process_spectrum",
    "none": "none",
    "answer": "none",
    "explain": "none",
}

STEP_TYPE_ALIASES = {
    "cut": "cut",
    "crop": "cut",
    "裁剪": "cut",
    "截取": "cut",
    "denoise": "denoise",
    "denoising": "denoise",
    "去噪": "denoise",
    "降噪": "denoise",
    "baseline": "baseline",
    "baseline correction": "baseline",
    "基线": "baseline",
    "基线校正": "baseline",
}

_NUMBER_PATTERN = re.compile(
    r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
)


def _label_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    text = text.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", text)


def _compact_key(value: Any) -> str:
    return _label_key(value).replace(" ", "")


def _lookup_alias(value: Any, aliases: Dict[str, str]) -> str:
    key = _label_key(value)
    compact = key.replace(" ", "")
    normalized: Dict[str, str] = {}
    for name, result in aliases.items():
        normalized[_label_key(name)] = result
        normalized[_compact_key(name)] = result
    return normalized.get(key) or normalized.get(compact) or ""


def _get_param(params: Dict[str, Any], *names: str, default: Any = None) -> Any:
    normalized = {_compact_key(key): value for key, value in params.items()}
    for name in names:
        value = normalized.get(_compact_key(name))
        if value is not None:
            return value
    return default


def empty_command() -> Dict[str, Any]:
    return {
        "action": "none",
        "mode": "replace",
        "steps": [],
        "reason": "",
        "requires_confirmation": False,
        "warnings": [],
    }


def _is_default_text(value: Any) -> bool:
    return _label_key(value) in {
        "",
        "default",
        "auto",
        "automatic",
        "默认",
        "自动",
        "使用默认值",
    }


def _parse_number(value: Any) -> Tuple[Any, bool]:
    if isinstance(value, bool) or value is None:
        return None, False
    if isinstance(value, (int, float)):
        number = float(value)
        return (number, math.isfinite(number))

    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    if _is_default_text(text):
        return None, False

    power_match = re.search(
        r"([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:\^|\*\*)\s*([-+]?\d+)",
        text,
    )
    if power_match:
        try:
            number = float(power_match.group(1)) ** int(power_match.group(2))
            return (number, math.isfinite(number))
        except (OverflowError, ValueError):
            return None, False

    match = _NUMBER_PATTERN.search(text)
    if not match:
        return None, False
    try:
        number = float(match.group(0))
        return (number, math.isfinite(number))
    except ValueError:
        return None, False


def _coerce_float(
    value: Any,
    default: float,
    field: str,
    minimum: float,
    maximum: float,
    warnings: List[str],
    *,
    percentage: bool = False,
) -> float:
    number, valid = _parse_number(value)
    if not valid:
        warnings.append(f"{field} was not usable; defaulted to {default:g}")
        number = default
    else:
        text = unicodedata.normalize("NFKC", str(value)).strip()
        if percentage and "%" in text:
            number /= 100.0

    bounded = max(minimum, min(maximum, float(number)))
    if bounded != float(number):
        warnings.append(f"{field} was outside the safe range; limited to {bounded:g}")
    return bounded


def _coerce_int(
    value: Any,
    default: int,
    field: str,
    minimum: int,
    maximum: int,
    warnings: List[str],
) -> int:
    number = _coerce_float(value, float(default), field, minimum, maximum, warnings)
    integer = int(round(number))
    if number != integer:
        warnings.append(f"{field} was rounded to {integer}")
    return max(minimum, min(maximum, integer))


def _coerce_choice(
    value: Any,
    default: str,
    choices: Iterable[str],
    field: str,
    warnings: List[str],
) -> str:
    text = _compact_key(value)
    for choice in choices:
        if _compact_key(choice) in text:
            return choice
    warnings.append(f"{field} was not usable; defaulted to {default}")
    return default


def _point_count(context: Dict[str, Any]) -> int:
    for key in ("raw_point_count", "selected_point_count"):
        value = context.get(key)
        if isinstance(value, int) and value > 0:
            return value
    for key in ("raw_wavenumber", "raw_intensity"):
        value = context.get(key)
        if isinstance(value, (list, tuple)) and value:
            return len(value)
    return 0


def _default_range(context: Dict[str, Any]) -> Tuple[float, float]:
    value = context.get("raw_wavenumber_range")
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            start, end = float(value[0]), float(value[1])
            if math.isfinite(start) and math.isfinite(end) and start != end:
                return min(start, end), max(start, end)
        except (TypeError, ValueError):
            pass

    values = context.get("raw_wavenumber")
    if isinstance(values, (list, tuple)) and len(values) >= 2:
        try:
            return min(float(v) for v in values), max(float(v) for v in values)
        except (TypeError, ValueError):
            pass
    return 0.0, 4000.0


def _normalize_params(
    step_type: str,
    method: str,
    raw_params: Any,
    context: Dict[str, Any],
    warnings: List[str],
) -> Dict[str, Any]:
    params = raw_params if isinstance(raw_params, dict) else {}
    if method in METHODS and method not in ('sg','wtd'):
        spec=METHODS[method]
        aliases={'lam':('lambda','lambda_','平滑参数'),'diff_order':('order_','差分阶数'),'max_half_window':('half_window',),'loops':('iterations',),'half_k_threshold':('peak_threshold',)}
        return {key:(_coerce_int if rule.get('integer') else _coerce_float)(
            _get_param(params,key,*aliases.get(key,()),default=rule['default']),rule['default'],step_type+'.'+key,rule['min'],rule['max'],warnings)
            for key,rule in spec['params'].items()}

    if step_type == "cut":
        default_start, default_end = _default_range(context)
        start = _coerce_float(
            _get_param(
                params,
                "start",
                "start_wavenumber",
                "min",
                "from",
                "起始",
                "起始波数",
                default=default_start,
            ),
            default_start,
            "cut.start",
            -1e9,
            1e9,
            warnings,
        )
        end = _coerce_float(
            _get_param(
                params,
                "end",
                "end_wavenumber",
                "max",
                "to",
                "结束",
                "结束波数",
                default=default_end,
            ),
            default_end,
            "cut.end",
            -1e9,
            1e9,
            warnings,
        )
        if start == end:
            warnings.append("cut range was empty; restored the current spectrum range")
            start, end = default_start, default_end
        return {"start": start, "end": end}

    if step_type == "denoise":
        if method == "sg":
            point_count = _point_count(context)
            max_window = 10001
            if point_count > 2:
                max_window = min(10001,max(3, point_count))
                if max_window % 2 == 0:
                    max_window -= 1
            order_max = min(20, max(0, point_count - 1)) if point_count else 20
            window = _coerce_int(
                _get_param(params, "window_size", "window", "frame", "窗口", default=7),
                7,
                "denoise.window_size",
                3,
                max_window,
                warnings,
            )
            order = _coerce_int(
                _get_param(params, "order", "poly_order", "polynomial_order", "阶数", default=3),
                3,
                "denoise.order",
                0,
                order_max,
                warnings,
            )
            if window % 2 == 0:
                window += 1
                if window > max_window:
                    window = max(3, max_window)
                warnings.append(f"denoise.window_size was adjusted to odd value {window}")
            if window <= order:
                order = max(1, window - 2)
                warnings.append(f"denoise.order was reduced to {order} to fit the window")
            return {"window_size": window, "order": order}

        if method == "wtd":
            wavelet = _coerce_choice(
                _get_param(params, "wavelet", "wave", "小波", default="db3"),
                "db3",
                [f"db{index}" for index in range(1, 10)],
                "denoise.wavelet",
                warnings,
            )
            level = _coerce_int(
                _get_param(params, "level", "decomposition_level", "层级", default=3),
                3,
                "denoise.level",
                1,
                20,
                warnings,
            )
            return {"wavelet": wavelet, "level": level}

        if method == "peer":
            loops = _coerce_int(
                _get_param(params, "loops", "iterations", "repeat", "循环", default=3),
                3,
                "denoise.loops",
                1,
                20,
                warnings,
            )
            threshold = _coerce_int(
                _get_param(
                    params,
                    "half_k_threshold",
                    "half_k",
                    "peak_threshold",
                    "threshold",
                    "寻峰",
                    default=2,
                ),
                2,
                "denoise.half_k_threshold",
                1,
                20,
                warnings,
            )
            return {"loops": loops, "half_k_threshold": threshold}

        if method == "tsvd":
            threshold = _coerce_float(
                _get_param(params, "threshold", "cutoff", "ratio", "阈值", default=1e-3),
                1e-3,
                "denoise.threshold",
                1e-8,
                1.0,
                warnings,
            )
            return {"threshold": threshold}

    if step_type == "baseline":
        if method in {"airpls", "airpls_old", "aspls", "aabs", "irsqr"}:
            lam = _coerce_float(
                _get_param(
                    params,
                    "lam",
                    "lambda",
                    "lambda_",
                    "smoothness",
                    "平滑参数",
                    default=1e7,
                ),
                1e7,
                "baseline.lam",
                1e2,
                1e12,
                warnings,
            )
            diff_order = _coerce_int(
                _get_param(
                    params,
                    "diff_order",
                    "order_",
                    "difference_order",
                    "order",
                    "差分阶数",
                    default=2,
                ),
                2,
                "baseline.diff_order",
                1,
                3,
                warnings,
            )
            quantile = _coerce_float(
                _get_param(
                    params,
                    "quantile",
                    "p",
                    "quantile_level",
                    "分位数",
                    default=0.01,
                ),
                0.01,
                "baseline.quantile",
                0.001,
                0.49,
                warnings,
                percentage=True,
            )
            return {"lam": lam, "diff_order": diff_order, "quantile": quantile}

        if method in {"imodpoly", "penalizedpoly"}:
            order = _coerce_int(
                _get_param(
                    params,
                    "poly_order",
                    "polynomial_order",
                    "order_",
                    "order",
                    "多项式阶数",
                    default=3,
                ),
                3,
                "baseline.poly_order",
                1,
                5,
                warnings,
            )
            return {"poly_order": order}

        if method in {"snip", "rollingball", "mormol"}:
            half_window = _coerce_int(
                _get_param(
                    params,
                    "half_window",
                    "max_half_window",
                    "window",
                    "窗口",
                    default=40,
                ),
                40,
                "baseline.half_window",
                2,
                2000,
                warnings,
            )
            return {"half_window": half_window}

    return {}


def validate_command(
    raw_command: Any,
    context: Dict[str, Any],
    surface: str = "spectral",
) -> Tuple[Dict[str, Any], List[str]]:
    """Return a safe, normalized command and structural validation errors.

    Numeric and formatting problems are repaired with bounded defaults and
    returned as warnings. Unknown actions, step types, and algorithms remain
    non-executable.
    """

    errors: List[str] = []
    warnings: List[str] = []
    if not isinstance(raw_command, dict):
        return empty_command(), ["The model did not return a command object"]

    expected_action = {
        "spectral": "process_spectrum",
        "hyperspectral": "process_hyperspectral",
    }.get(surface)
    if expected_action is None:
        return empty_command(), [f"Unsupported assistant surface: {surface}"]

    action = _lookup_alias(raw_command.get("action", "none"), ACTION_ALIASES)
    if action in {"", "none"}:
        command = empty_command()
        command["reason"] = str(raw_command.get("reason", "")).strip()[:500]
        return command, []
    # Generic models sometimes return process_spectrum for a hyperspectral
    # request. Normalize that generic action only on the hyperspectral surface.
    if surface == "hyperspectral" and action == "process_spectrum":
        action = "process_hyperspectral"
    if action != expected_action:
        return empty_command(), [f"Unsupported action: {raw_command.get('action')}"]

    status = context.get("status") if isinstance(context, dict) else {}
    if not isinstance(status, dict) or not status.get("has_data"):
        subject = "hyperspectral dataset" if surface == "hyperspectral" else "spectrum"
        return empty_command(), [f"Load a {subject} before asking the assistant to process it"]

    mode_key = _label_key(raw_command.get("mode", raw_command.get("operation", "replace")))
    if mode_key in {"append", "add", "追加"}:
        mode = "append"
    elif mode_key in {"replace", "set", "替换"}:
        mode = "replace"
    else:
        mode = "replace"
        warnings.append("mode was not recognized; defaulted to replace")

    raw_steps = raw_command.get("steps", [])
    if not isinstance(raw_steps, list) or not raw_steps:
        return empty_command(), ["At least one processing step is required"]

    scope = "dataset"
    if surface == "hyperspectral":
        scope_key = _label_key(raw_command.get("scope", "dataset"))
        dataset_scopes = {
            "dataset",
            "whole dataset",
            "entire dataset",
            "cube",
            "all data",
            "all spectra",
            "整个数据集",
            "全部数据",
            "整个高光谱数据集",
        }
        if scope_key not in {_label_key(value) for value in dataset_scopes}:
            return empty_command(), [
                "Hyperspectral operations currently support the entire dataset only; "
                "single-pixel and single-time-point execution is not available"
            ]

    steps: List[Dict[str, Any]] = []
    for index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            errors.append(f"Step {index + 1} is not an object")
            continue

        step_type = _lookup_alias(raw_step.get("type", ""), STEP_TYPE_ALIASES)
        if step_type not in {"cut", "denoise", "baseline"}:
            errors.append(f"Step {index + 1} has unsupported type: {raw_step.get('type')}")
            continue

        if step_type == "cut":
            method = "cut"
        elif step_type == "denoise":
            method = _lookup_alias(raw_step.get("method", ""), DENOISE_ALIASES)
        else:
            method = _lookup_alias(raw_step.get("method", ""), BASELINE_ALIASES)
        if not method:
            errors.append(f"Step {index + 1} has unsupported method: {raw_step.get('method')}")
            continue

        params = dict(raw_step.get("params") or {}) if isinstance(raw_step.get("params"), dict) else {}
        for key, value in raw_step.items():
            if key not in {"type", "method", "params"} and key not in params:
                params[key] = value
        normalized = _normalize_params(step_type, method, params, context, warnings)
        steps.append({"type": step_type, "method": method, "params": normalized})

    if errors:
        command = empty_command()
        command["warnings"] = errors
        return command, errors

    command = {
        "action": expected_action,
        "mode": mode,
        "steps": steps,
        "reason": str(raw_command.get("reason", "")).strip()[:500],
        "requires_confirmation": True,
        "warnings": warnings,
    }
    if surface == "hyperspectral":
        command["scope"] = scope
    return command, []
