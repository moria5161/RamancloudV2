"""Authenticated, persistent workspace chat; model plans never execute here."""
import hashlib
import json
import logging
import threading
import uuid
from typing import Any, Dict
from urllib.error import HTTPError, URLError

import numpy as np
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

import ai_assistant as engine
from ai_workflow import REGISTRY, diagnostics, local_plan, number, respect_constraints, validate_spectrum, validate_steps
from assistant_commands import empty_command, validate_command

LOG = logging.getLogger(__name__)
SURFACES = {"spectral", "hyperspectral", "extra-tools"}
ARRAY_PAIRS = [(prefix + "wavenumber", prefix + "intensity") for prefix in
               ("raw_", "processed_", "selected_", "selected_processed_")]
from legacy_algorithms import METHODS
TSVD = METHODS['tsvd']


class Workspace(BaseModel):
    surface: str = "spectral"
    context: Dict[str, Any] = Field(default_factory=dict)


class ChatPayload(Workspace):
    conversation_id: str = Field(..., max_length=64)
    message: str = Field(..., min_length=1, max_length=2000)
    language: str = "zh"
    allow_ai: bool = False


class AppliedPayload(BaseModel):
    message_id: str = Field(..., max_length=64)
    analysis_run_id: str = Field(..., max_length=64)


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)


def fingerprint(value):
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


def clean_context(surface, raw):
    if surface not in SURFACES:
        raise HTTPException(400, "不支持的对话工作区。")
    context = {"page": "single-spectrum" if surface == "spectral" else surface}
    for key in ("mode", "active_tab", "analysis_scope", "raw_dataset_id", "processed_dataset_id",
                "tool", "instrument", "conversion"):
        if isinstance(raw.get(key), str):
            context[key] = raw[key][:100]
    for key in ("preview_wavenumber", "processed_preview_wavenumber", "selected_series_index", "selected_file_count"):
        value = raw.get(key)
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
                raise HTTPException(400, "工作区坐标或索引无效。")
            context[key] = value
    if isinstance(raw.get("selected_pixel"), dict):
        pixel = raw["selected_pixel"]
        if all(isinstance(pixel.get(k), int) and 0 <= pixel[k] <= 100000 for k in ("x", "y")):
            context["selected_pixel"] = {k: pixel[k] for k in ("x", "y")}
    shape = raw.get("shape")
    if shape is not None:
        if not isinstance(shape, list) or not 1 <= len(shape) <= 3 or not all(isinstance(n, int) and 0 < n <= 100000 for n in shape):
            raise HTTPException(400, "数据维度无效。")
        context["shape"] = shape
    for wave_key, values_key in ARRAY_PAIRS:
        wave, values = raw.get(wave_key), raw.get(values_key)
        if wave is None and values is None:
            continue
        try:
            if not isinstance(wave, list) or not isinstance(values, list) or len(wave) > 20000 or len(values) > 20000:
                raise ValueError("需要不超过 20000 个点的一维数组。")
            x, y = validate_spectrum(wave, values)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, "对话数据校验失败：" + str(exc)[:200])
        context[wave_key], context[values_key] = x.tolist(), y.tolist()
    for key in ("raw_preview", "processed_preview"):
        if raw.get(key) is None:
            continue
        try:
            if not isinstance(raw[key], list) or not raw[key] or not all(isinstance(row, list) for row in raw[key]) or sum(len(row) for row in raw[key]) > 20000:
                raise ValueError()
            matrix = np.asarray(raw[key], dtype=float)
            if matrix.ndim != 2 or not 1 <= matrix.size <= 20000 or not np.isfinite(matrix).all():
                raise ValueError()
        except (TypeError, ValueError):
            raise HTTPException(400, "图像摘要应为不超过 20000 个数值的二维数组。")
        context[key] = matrix.tolist()
    pipeline = raw.get("pipeline", [])
    if not isinstance(pipeline, list) or len(pipeline) > 10:
        raise HTTPException(400, "处理流程最多包含 10 个步骤。")
    context["pipeline"] = []
    for step in pipeline:
        if not isinstance(step, dict) or not isinstance(step.get("params", {}), dict):
            raise HTTPException(400, "处理步骤格式错误。")
        params = step.get("params", {})
        if len(params) > 12 or not all(isinstance(v, (str, float, int)) and not isinstance(v, bool)
                                     and (not isinstance(v, (int, float)) or np.isfinite(v)) for v in params.values()):
            raise HTTPException(400, "处理参数无效。")
        context["pipeline"].append(dict(type=str(step.get("type", ""))[:30],
                                        method=str(step.get("method", ""))[:30], params=params))
    context["status"] = dict(has_data="raw_wavenumber" in context,
                             has_processed_result="processed_wavenumber" in context,
                             has_baseline=bool(raw.get("status", {}).get("has_baseline")) if isinstance(raw.get("status"), dict) else False)
    if surface == "hyperspectral":
        context["analysis_target"] = context.get("selected_pixel") or {"index": context.get("selected_series_index"), "wavenumber": context.get("preview_wavenumber")}
    return context


def source_key(surface, context):
    return fingerprint([surface, context.get("raw_dataset_id"), context.get("mode"),
                        context.get("raw_wavenumber"), context.get("raw_intensity")])


def checked_command(raw_command, context, surface, goal):
    command, errors = validate_command(raw_command, context, surface)
    if errors or not command["requires_confirmation"]:
        return command, errors
    try:
        if surface == "hyperspectral" and engine.requests_local_hyperspectral_scope(goal):
            raise ValueError("当前只支持处理整个数据集，不支持只处理单个像素或时间点。")
        registry = REGISTRY + ([TSVD] if surface == "hyperspectral" else [])
        aliases = {"aspls": "airpls", "aabs": "airpls", "irsqr": "airpls",
                   "penalizedpoly": "imodpoly", "rollingball": "snip", "mormol": "snip"}
        for step in command["steps"]:
            if step["method"] in aliases:
                step["method"] = aliases[step["method"]]
                command["warnings"].append("使用平台已有的兼容实现，请检查最终算法与参数。")
        combined = (context["pipeline"] if command["mode"] == "append" else []) + command["steps"]
        validated = validate_steps(combined, context["raw_wavenumber"], registry=registry)
        proposed = validated[len(context["pipeline"]):] if command["mode"] == "append" else validated
        respect_constraints(proposed, goal, "")
        command["steps"] = [{k: s[k] for k in ("type", "method", "params", "label")} for s in proposed]
        command["scope"] = "dataset" if surface == "hyperspectral" else "spectrum"
    except (ValueError, KeyError, TypeError) as exc:
        return empty_command(), [str(exc)[:200]]
    return command, []


def rules_reply(language, surface, context, messages):
    chinese = language == "zh"
    goal = messages[-1]["content"]
    intent = engine._keyword_intent(goal)
    command = empty_command()
    grounded = engine._model_context(context)
    if intent == "OPERATE" and surface in {"spectral", "hyperspectral"}:
        if not context["status"]["has_data"]:
            return ("请先加载数据，当前没有生成处理方案。" if chinese else "Load data before requesting a processing plan."), command
        if surface == "hyperspectral" and engine.requests_local_hyperspectral_scope(goal):
            return ("目前只能处理整个数据集，不能只处理单个像素或时间点。数据尚未改变。" if chinese else "Only whole-dataset processing is supported. Data was not changed."), command
        x, y = np.asarray(context["raw_wavenumber"]), np.asarray(context["raw_intensity"])
        plan = local_plan(goal, "", diagnostics(x, y))
        if plan.get("clarification"):
            return plan["clarification"], command
        candidate = dict(action="process_hyperspectral" if surface == "hyperspectral" else "process_spectrum",
                         scope="dataset", mode="replace", steps=plan["steps"], reason=plan.get("summary", ""))
        command, errors = checked_command(candidate, context, surface, goal)
        if errors:
            return ("未生成可执行方案：" if chinese else "No executable plan: ") + " ".join(errors), empty_command()
        return ("已生成本地规则方案，确认执行前数据不会改变。" if chinese else "A local-rule plan is ready. Data will not change until you confirm."), command
    text = []
    lower = goal.lower()
    if "sg" in lower or "savitzky" in lower:
        text.append("SG 用局部多项式拟合平滑数据。窗口必须为奇数；窗口太大可能削弱窄峰。" if chinese else "SG smooths with local polynomial fits. Large windows can weaken narrow peaks.")
    elif "小波" in goal or "wavelet" in lower or "wtd" in lower:
        text.append("小波降噪对细节系数做阈值处理，再重构信号。阈值与分解层数会影响峰形。" if chinese else "Wavelet denoising thresholds detail coefficients before reconstruction; review peak preservation.")
    elif "基线" in goal or "baseline" in lower:
        text.append("基线校正估计背景并从强度中减去它。平台 airpls 接口是 AsLS/Whittaker 兼容实现，不能等同于原版 airPLS。" if chinese else "Baseline correction subtracts estimated background. The platform airpls interface uses an AsLS/Whittaker-compatible implementation.")
    comparison = grounded.get("spectrum_comparison")
    summary = grounded.get("raw_analysis") or (comparison or {}).get("raw")
    if summary:
        text.append((f"当前{'平均' if surface == 'hyperspectral' else ''}光谱：{summary['point_count']} 个点，"
                     f"波数范围 {summary['wavenumber_range']}，噪声代理标准差 {summary['noise_proxy_std']}。") if chinese
                    else f"Current spectrum: {summary['point_count']} points, range {summary['wavenumber_range']}, noise proxy {summary['noise_proxy_std']}.")
    if comparison:
        text.append((f"处理后的噪声代理变化为 {comparison['noise_change_percent']}%。这只是启发式指标，不代表真实实验信噪比。") if chinese
                    else f"Noise proxy changed by {comparison['noise_change_percent']}%. This is not a measured experimental SNR.")
    if surface == "hyperspectral":
        text.append("平均谱不能代表每个像素；热图颜色变化不能直接证明峰位移动。处理建议针对整个数据集。" if chinese else "Mean spectra do not describe every pixel. Heatmap color changes do not prove peak shifts. Operations target the whole dataset.")
    if surface == "extra-tools":
        text.append("文件工具支持拆分、合并与 Horiba/Nanophoton 格式转换；当前对话没有执行文件操作。" if chinese else "Tools support splitting, merging and Horiba/Nanophoton conversion. No file operation was executed by this chat.")
    if not text:
        text.append("可以询问算法原理；加载数据后可查看诊断摘要或请求待确认的处理建议。当前为本地规则，不是大模型回答。" if chinese else "Ask about preprocessing or load a spectrum for diagnostics. This is a local-rule response, not a model answer.")
    return "\n\n".join(text), command


def install_assistant(app, h):
    db, auth, now = h["db_connect"], h["get_current_user"], h["iso_now"]
    gate, slots, busy = threading.RLock(), threading.BoundedSemaphore(4), set()
    with db() as conn:
        conn.execute(f"""CREATE TABLE IF NOT EXISTS assistant_conversations (
            id {h['ID_SQL']} PRIMARY KEY, user_id {h['ID_SQL']} NOT NULL,
            surface {h['SHORT_SQL']} NOT NULL, context_key {h['ID_SQL']} NOT NULL,
            messages_json {h['JSON_SQL']} NOT NULL, created_at {h['DATE_SQL']} NOT NULL,
            updated_at {h['DATE_SQL']} NOT NULL, UNIQUE(user_id, surface, context_key),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) {h['TABLE_OPTIONS']}""")

    def owned(conn, cid, user):
        row = conn.execute("SELECT * FROM assistant_conversations WHERE id = ? AND user_id = ?", (cid, user["id"])).fetchone()
        if row is None:
            raise HTTPException(404, "对话不存在。")
        return row

    def view(row):
        return dict(id=row["id"], surface=row["surface"], messages=json.loads(row["messages_json"]))

    @app.get("/api/assistant/config")
    def get_config(user=Depends(auth)):
        settings = engine.assistant_settings()
        from ai_workflow import model_availability
        return dict({k: settings[k] for k in ("provider", "provider_name", "model", "configured")}, **model_availability(settings))

    @app.post("/api/assistant/conversations")
    def open_conversation(payload: Workspace, user=Depends(auth)):
        context = clean_context(payload.surface, payload.context)
        key = source_key(payload.surface, context)
        with gate, db() as conn:
            row = conn.execute("SELECT * FROM assistant_conversations WHERE user_id = ? AND surface = ? AND context_key = ?",
                               (user["id"], payload.surface, key)).fetchone()
            if row is None:
                cid, timestamp = uuid.uuid4().hex, now()
                conn.execute("INSERT INTO assistant_conversations (id,user_id,surface,context_key,messages_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                             (cid, user["id"], payload.surface, key, "[]", timestamp, timestamp))
                row = owned(conn, cid, user)
            return dict(view(row), snapshot=fingerprint(context))

    @app.get("/api/assistant/conversations/{cid}")
    def get_conversation(cid: str, user=Depends(auth)):
        with db() as conn:
            return view(owned(conn, cid, user))

    @app.delete("/api/assistant/conversations/{cid}")
    def clear_conversation(cid: str, user=Depends(auth)):
        with gate, db() as conn:
            owned(conn, cid, user)
            if cid in busy:
                raise HTTPException(409, "对话请求进行中，请稍后清空。")
            conn.execute("UPDATE assistant_conversations SET messages_json = '[]', updated_at = ? WHERE id = ?", (now(), cid))
        return dict(id=cid, messages=[])

    @app.post("/api/assistant/chat")
    def chat(payload: ChatPayload, user=Depends(auth)):
        context = clean_context(payload.surface, payload.context)
        cid = payload.conversation_id
        with gate, db() as conn:
            row = owned(conn, cid, user)
            if row["surface"] != payload.surface or row["context_key"] != source_key(payload.surface, context):
                raise HTTPException(409, "数据源已变化，请切换到当前数据的对话。")
            if cid in busy or not slots.acquire(blocking=False):
                raise HTTPException(429, "对话服务繁忙，请稍后重试。")
            busy.add(cid)
        try:
            history = json.loads(row["messages_json"])
            if len(history) >= 200:
                raise HTTPException(400, "本对话已达 100 轮，请清空后开始新对话。")
            message = payload.message.strip()
            if not message:
                raise HTTPException(400, "消息不能为空。")
            messages = history + [dict(id=uuid.uuid4().hex, role="user", content=message)]
            language = "zh" if payload.language == "zh" else "en"
            answer, command = rules_reply(language, payload.surface, context, messages)
            provider, model, fallback = "local_rules", "", "未授权调用模型。" if language == "zh" else "Model use was not authorized."
            settings = engine.assistant_settings()
            if payload.allow_ai and settings["configured"]:
                try:
                    if engine._keyword_intent(message) == "OPERATE" and payload.surface in {"spectral", "hyperspectral"}:
                        if not context["status"]["has_data"]:
                            raise ValueError("Load data first.")
                        if payload.surface == "hyperspectral" and engine.requests_local_hyperspectral_scope(message):
                            raise ValueError("Only whole-dataset processing is supported.")
                        result = engine.plan_processing_command(language, context, messages, payload.surface)
                        command, errors = checked_command(result["command"], context, payload.surface, message)
                        if errors:
                            raise ValueError("Model plan failed platform validation.")
                        answer = ("已生成待确认方案，尚未执行。" if language == "zh" else "A plan is ready for confirmation. It has not been executed.") if command["requires_confirmation"] else result["message"]
                    else:
                        result = engine.chat_with_assistant(language, payload.surface, context, messages)
                        answer, command = result["message"], empty_command()
                    provider, model, fallback = settings["provider"], settings["model"], ""
                except HTTPError as exc:
                    reason = {401: "密钥验证失败", 402: "余额不足或需要付费", 403: "账号权限不足", 429: "接口限流"}.get(exc.code, "模型接口异常")
                    fallback = reason + "，已使用本地规则。" if language == "zh" else f"Model returned HTTP {exc.code}; using local rules."
                    answer, command = rules_reply(language, payload.surface, context, messages)
                except (RuntimeError, ValueError, TypeError, KeyError, IndexError, URLError, OSError):
                    LOG.warning("Assistant model unavailable or returned an invalid response")
                    fallback = "模型连接失败或输出未通过校验，已使用本地规则。" if language == "zh" else "Model unavailable or output invalid; using local rules."
                    answer, command = rules_reply(language, payload.surface, context, messages)
            elif payload.allow_ai:
                fallback = "未配置模型密钥，已使用本地规则。" if language == "zh" else "No model key configured; using local rules."
            reply = dict(id=uuid.uuid4().hex, role="assistant", content=answer[:6000], provider=provider,
                         model=model, fallback_reason=fallback, command=command, snapshot=fingerprint(context), applied=False)
            if command["requires_confirmation"]:
                combined = (context["pipeline"] if command["mode"] == "append" else []) + command["steps"]
                reply["expected_steps"] = [{k: s[k] for k in ("type", "method", "params")} for s in combined]
                reply["input_fingerprint"] = fingerprint([context.get("raw_wavenumber"), context.get("raw_intensity")])
                reply["input_dataset_id"] = context.get("raw_dataset_id")
            messages.append(reply)
            with gate, db() as conn:
                owned(conn, cid, user)
                conn.execute("UPDATE assistant_conversations SET messages_json = ?, updated_at = ? WHERE id = ?", (encode(messages), now(), cid))
            return dict(conversation_id=cid, messages=messages, reply=reply)
        finally:
            with gate:
                busy.discard(cid)
                slots.release()

    @app.post("/api/assistant/conversations/{cid}/applied")
    def applied(cid: str, payload: AppliedPayload, user=Depends(auth)):
        with gate, db() as conn:
            row = owned(conn, cid, user)
            if cid in busy:
                raise HTTPException(409, "对话请求进行中。")
            run = conn.execute("SELECT * FROM analysis_runs WHERE id = ? AND user_id = ?", (payload.analysis_run_id, user["id"])).fetchone()
            if run is None:
                raise HTTPException(404, "没有找到当前账号的分析结果。")
            h['get_analysis_run_row'](conn, payload.analysis_run_id, user)
            messages = json.loads(row["messages_json"])
            reply = next((m for m in messages if m["id"] == payload.message_id and m["role"] == "assistant"), None)
            if reply is None or not reply.get("command", {}).get("requires_confirmation"):
                raise HTTPException(400, "没有可确认的处理建议。")
            if reply.get("applied") and reply.get("analysis_run_id") != payload.analysis_run_id:
                raise HTTPException(409, "该建议已关联执行结果。")
            expected_type = "hyperspectral" if row["surface"] == "hyperspectral" else "spectrum"
            if run["analysis_type"] != expected_type or json.loads(run["steps_json"]) != reply["expected_steps"]:
                raise HTTPException(400, "分析记录与待确认方案不一致。")
            source = json.loads(run["input_json"])
            if expected_type == "spectrum" and fingerprint([source["wavenumber"], source["intensity"]]) != reply["input_fingerprint"]:
                raise HTTPException(400, "分析记录的数据源不一致。")
            if expected_type == "hyperspectral" and source.get("dataset_id") != reply.get("input_dataset_id"):
                raise HTTPException(400, "分析记录的数据集不一致。")
            reply.update(applied=True, analysis_run_id=payload.analysis_run_id)
            conn.execute("UPDATE assistant_conversations SET messages_json = ?, updated_at = ? WHERE id = ?", (encode(messages), now(), cid))
        return dict(id=cid, messages=messages)
