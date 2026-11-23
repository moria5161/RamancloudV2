"""Bounded candidate review and immutable-prefix reuse for spectrum workflows."""
import copy
import json
import re

import numpy as np
from scipy.signal import find_peaks
from preprocessing.despike import REPAIR_POLICY


DEFAULT_PREPROCESS_GOAL = "先去鬼峰，再适度降噪，最后校正缓慢变化的基线背景，保留主要峰和峰形，不进行归一化。"


def step_signature(step):
    return {key: step.get(key) for key in ("type", "method", "params", "enabled", "implementation")}


def reusable_prefix(steps, records):
    length = 0
    for step, record in zip(steps, records):
        if record.get("status") not in {"done", "skipped"} or step_signature(step) != step_signature(record.get("step", {})):
            break
        if step.get('type') == 'despike' and step.get('enabled', True) and record.get('status') != 'skipped' and (record.get('details') or {}).get('repair_policy') != REPAIR_POLICY:
            break
        length += 1
    return length


def checked_region(region, wave):
    if region is None:
        return None
    start, end = region["start"], region["end"]
    axis = np.asarray(wave, dtype=float)
    if not np.isfinite([start, end]).all() or start >= end or start < axis.min() or end > axis.max():
        raise ValueError("选择的波段必须位于原始波数范围内，起点小于终点。")
    if np.count_nonzero((axis >= start) & (axis <= end)) < 8:
        raise ValueError("选择的波段至少应保留 8 个数据点。")
    return dict(start=float(start), end=float(end))


def scoped_steps(steps, region, wave):
    if region is None:
        return copy.deepcopy(steps)
    result = [copy.deepcopy(step) for step in steps if step.get("type") != "cut"]
    if region["start"] > min(wave) or region["end"] < max(wave):
        result.insert(0, dict(id="selected-band", type="cut", method="cut", params=region,
                              enabled=True, reason="用户手动选择的处理波段，原始文件保持不变。"))
    return result


def peak_comparison(wave, original, processed):
    span = max(float(np.ptp(original)), 1e-12)
    peaks, props = find_peaks(original, prominence=span * .04)
    output, out_props = find_peaks(processed, prominence=span * .02)
    top = np.argsort(props["prominences"])[-8:]
    tolerance = max(float(np.median(np.abs(np.diff(wave)))) * 3, 1e-12)
    matched, ratios, used = 0, [], set()
    for index in top:
        choices = [i for i in range(len(output)) if i not in used and abs(wave[output[i]] - wave[peaks[index]]) <= tolerance]
        if choices:
            nearest = min(choices, key=lambda i: abs(wave[output[i]] - wave[peaks[index]]))
            used.add(nearest)
            matched += 1
            ratios.append(float(out_props["prominences"][nearest] / props["prominences"][index]))
    return (matched / len(top) if len(top) else None), (float(np.median(ratios)) if ratios else None)


def compare_candidates(steps, raw, evaluate, validate, diagnose, goal):
    proposals = [("initial", "初始方案", copy.deepcopy(steps))]
    # Change only numerical strength, never add operations or override explicit numeric requests.
    explicit = bool(re.search(r"(?:窗口|window|lam|λ|阶数|order|层数|level)\D{0,12}\d", goal, re.I))
    if not explicit:
        for name, factor, delta in [("gentle", .5, -2), ("stronger", 2., 2)]:
            variant = copy.deepcopy(steps)
            for step in variant:
                if not step.get("enabled", True):
                    continue
                params = step["params"]
                if step["method"] == "sg":
                    params["window_size"] = max(params["order"] + 1, params["window_size"] + delta, 3)
                    if params["window_size"] % 2 == 0:
                        params["window_size"] += 1
                elif step["method"] == "airpls":
                    params["lam"] = max(10., min(1e9, params["lam"] * factor))
                elif step["method"] == "wtd":
                    params["level"] = max(1, params["level"] + (-1 if delta < 0 else 1))
                step["reason"] = str(step.get("reason", "")) + (" 候选试跑：较保守参数。" if delta < 0 else " 候选试跑：较强参数。")
            proposals.append((name, "保守参数" if delta < 0 else "增强参数", variant))
    rows, signatures = [], set()
    for cid, label, candidate in proposals[:3]:
        try:
            valid = validate(candidate, raw["wavenumber"])
            signature = json.dumps([step_signature(s) for s in valid], sort_keys=True)
            if signature in signatures:
                continue
            signatures.add(signature)
            trace = evaluate(valid)
            last = trace[-1]["after"]
            wave, output = np.asarray(last["wavenumber"]), np.asarray(last["intensity"])
            source_x, source_y = np.asarray(raw["wavenumber"]), np.asarray(raw["intensity"])
            if source_x[0] > source_x[-1]:
                source_x, source_y = source_x[::-1], source_y[::-1]
            original = np.interp(wave, source_x, source_y)
            residual = original - output
            denoising = next((r for r in reversed(trace) if r["step"]["type"] == "denoise" and r["step"]["enabled"]), None)
            removed_noise = np.asarray(denoising["before"]["intensity"]) - np.asarray(denoising["after"]["intensity"]) if denoising else np.zeros_like(output)
            retention, amplitude = peak_comparison(wave, original, output)
            before, after = diagnose(wave, original), diagnose(wave, output)
            noise = min(2., after["noise_ratio"] / max(before["noise_ratio"], 1e-9))
            residual_rms = float(np.sqrt(np.mean(removed_noise ** 2)))
            residual_ratio = residual_rms / max(float(np.ptp(original)), 1e-12)
            penalty = .45 * min(1., noise) + .30 * (1. - retention if retention is not None else 0.)
            penalty += .15 * min(1., abs(1. - amplitude)) if amplitude is not None else .15
            penalty += .10 * min(1., residual_ratio)
            indices = np.unique(np.linspace(0, len(wave) - 1, min(256, len(wave)), dtype=int))
            rows.append(dict(id=cid, label=label, steps=valid, status="valid", score=round(100 * max(0., 1. - penalty), 2),
                             noise_ratio=after["noise_ratio"], peak_retention=retention, prominence_ratio=amplitude,
                             denoise_residual_rms=round(residual_rms, 8), residual_rms=round(float(np.sqrt(np.mean(residual ** 2))), 8),
                             points=len(wave), curves=dict(wavenumber=wave[indices].tolist(), original=original[indices].tolist(),
                             processed=output[indices].tolist(), residual=residual[indices].tolist()),
                             warnings=list(dict.fromkeys(w for record in trace for w in record["warnings"]))))
        except (ValueError, FloatingPointError, ArithmeticError) as exc:
            rows.append(dict(id=cid, label=label, status="invalid", error=str(exc)[:200]))
    successful = [row for row in rows if row["status"] == "valid"]
    if not successful:
        raise ValueError("候选方案试跑未成功，请检查数据或手动修改方案。")
    selected = max(successful, key=lambda row: row["score"])
    return selected["steps"], dict(candidates=rows, selected_candidate=selected["id"],
                                   evaluation_method="heuristic", evaluation_note="基于噪声、峰位置/显著度和降噪残差的启发式比较，不代表科学最优结论。")
