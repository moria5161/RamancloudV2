"""Assistant cases reuse the workflow suite's isolated HTTP server and database."""
import io
import json
import threading
from unittest.mock import patch
from urllib.error import HTTPError

import numpy as np
import ai_assistant as engine
import ai_workflow as workflow
from spectral_analysis import analyze_spectrum, compare_spectra


class AssistantCases:
    def test_assistant_diagnostic_peak_counts_and_cropped_peaks(self):
        wave = np.linspace(400, 1800, 2000)
        values = np.sin(np.linspace(0, 80 * np.pi, 2000))
        stats = analyze_spectrum(wave, values)
        self.assertGreater(stats["peak_count"], 12)
        self.assertEqual(len(stats["top_peaks"]), 12)
        cut = wave >= 1500
        comparison = compare_spectra(wave, values, wave[cut], values[cut])
        self.assertTrue(all(peak["raw_position"] >= 1500 for peak in comparison["matched_peak_changes"]))

    def test_assistant_unrelated_history_cannot_mark_plan_applied(self):
        room, context = self.assistant_open()
        reply = self.assistant_send(room, context, "帮我用 SG 降噪")[1]["reply"]
        run = self.call("/api/process", dict(wavenumber=context["raw_wavenumber"], intensity=context["raw_intensity"], steps=[], save_history=True))[1]["data"]["analysis_run"]
        code, _ = self.call(f"/api/assistant/conversations/{room['id']}/applied", dict(message_id=reply["id"], analysis_run_id=run["id"]))
        self.assertEqual(code, 400)

    def test_assistant_questions_never_generate_operation(self):
        room, context = self.assistant_open()
        with patch.object(engine, "assistant_settings", return_value=dict(provider="deepseek", model="mock", configured=True)), patch.object(engine, "chat_with_assistant", return_value=dict(message="解释而不是执行")), patch.object(engine, "plan_processing_command", side_effect=AssertionError("must not plan an operation")):
            result = self.assistant_send(room, context, "为什么降噪会影响峰形？", allow_ai=True)[1]
        self.assertFalse(result["reply"]["command"]["requires_confirmation"])

    def assistant_context(self):
        wave = np.linspace(400, 1800, 101)
        values = 0.01 * wave + 25 * np.exp(-((wave - 900) / 30) ** 2)
        return dict(raw_wavenumber=wave.tolist(), raw_intensity=values.tolist(), pipeline=[])

    def assistant_open(self, context=None, surface="spectral"):
        context = self.assistant_context() if context is None else context
        code, result = self.call("/api/assistant/conversations", dict(surface=surface, context=context))
        self.assertEqual(code, 200, result)
        return result, context

    def assistant_send(self, conversation, context, message="什么是 SG？", **extra):
        return self.call("/api/assistant/chat", dict(conversation_id=conversation["id"], context=context,
                         surface=conversation["surface"], message=message, language="zh", **extra))

    def test_assistant_auth_and_owner_isolation(self):
        self.assertEqual(self.request("/api/assistant/config")[0], 401)
        room, context = self.assistant_open()
        self.assertEqual(self.request("/api/assistant/conversations/" + room["id"], token=self.other["token"])[0], 404)
        self.assertEqual(self.request("/api/assistant/conversations/" + room["id"], token=self.other["token"], method="DELETE")[0], 404)
        settings = self.call("/api/assistant/config")[1]
        self.assertNotIn("api_key", settings)
        self.assertNotIn("base_url", settings)

    def test_assistant_local_consent_and_persistence(self):
        room, context = self.assistant_open()
        with patch.object(engine, "_call_model", side_effect=AssertionError("must not call a model")):
            code, result = self.assistant_send(room, context)
        self.assertEqual(code, 200, result)
        self.assertEqual(result["reply"]["provider"], "local_rules")
        self.assertFalse(result["reply"]["command"]["requires_confirmation"])
        reopened, _ = self.assistant_open(context)
        self.assertEqual(reopened["id"], room["id"])
        self.assertEqual(reopened["messages"], result["messages"])

    def test_assistant_command_requires_confirmed_history(self):
        context = self.assistant_context()
        context["raw_intensity"][0] += 0.002
        room, context = self.assistant_open(context)
        code, result = self.assistant_send(room, context, "帮我用 SG 降噪")
        self.assertEqual(code, 200, result)
        reply = result["reply"]
        self.assertTrue(reply["command"]["requires_confirmation"])
        self.assertNotIn("analysis_run_id", reply)
        payload = dict(wavenumber=context["raw_wavenumber"], intensity=context["raw_intensity"],
                       steps=reply["command"]["steps"], save_history=True, source_name="assistant_test")
        code, processed = self.call("/api/process", payload)
        self.assertEqual(code, 200, processed)
        run = processed["data"]["analysis_run"]
        self.assertIsNotNone(run)
        code, logged = self.call(f"/api/assistant/conversations/{room['id']}/applied", dict(message_id=reply["id"], analysis_run_id=run["id"]))
        self.assertEqual(code, 200, logged)
        self.assertTrue(logged["messages"][-1]["applied"])
        self.assertEqual(logged["messages"][-1]["analysis_run_id"], run["id"])

    def test_assistant_source_and_parameter_validation(self):
        room, context = self.assistant_open()
        changed = dict(context, raw_intensity=[value + 1 for value in context["raw_intensity"]])
        self.assertEqual(self.assistant_send(room, changed)[0], 409)
        malformed = dict(context, raw_intensity=[1])
        self.assertEqual(self.call("/api/assistant/conversations", dict(surface="spectral", context=malformed))[0], 400)
        self.assertEqual(self.assistant_send(room, context, message="")[0], 422)
        self.assertEqual(self.assistant_send(room, context, message=" " * 5)[0], 400)

    def test_assistant_deepseek_grounding_and_no_raw_arrays(self):
        room, context = self.assistant_open()
        settings = dict(provider="deepseek", provider_name="DeepSeek", model="test-chat", api_key="test-key",
                        configured=True, base_url="https://api.deepseek.com")
        context["secret"] = "must-not-leave-server"
        context["username"] = "must-not-leave-server"
        captured = []
        def response(request, **kwargs):
            captured.append(json.loads(request.data))
            return io.BytesIO(json.dumps(dict(choices=[dict(message=dict(content="SG 用局部拟合平滑。"), finish_reason="stop")])).encode())
        with patch.object(engine, "assistant_settings", return_value=settings), patch.object(workflow, "urlopen", side_effect=response):
            code, result = self.assistant_send(room, context, allow_ai=True)
        self.assertEqual(code, 200, result)
        self.assertEqual(result["reply"]["provider"], "deepseek")
        prompt = json.dumps(captured)
        grounded = json.loads(captured[0]["messages"][1]["content"].split("\n", 1)[1])
        self.assertNotIn("raw_wavenumber", grounded)
        self.assertNotIn("raw_intensity", grounded)
        self.assertNotIn("must-not-leave-server", prompt)
        self.assertIn("noise_proxy_std", prompt)
        self.assertFalse(captured[0]["stream"])

    def test_assistant_invalid_model_plan_falls_back(self):
        room, context = self.assistant_open()
        settings = dict(provider="deepseek", provider_name="DeepSeek", model="mock", configured=True)
        for candidate in [dict(action="process_spectrum", steps=[dict(type="execute", method="python", params={})]),
                          dict(action="process_spectrum", steps=[dict(type="cut", method="cut", params=dict(start=401, end=410)), dict(type="denoise", method="sg", params=dict(window_size=99))])]:
            with patch.object(engine, "assistant_settings", return_value=settings), patch.object(engine, "plan_processing_command", return_value=dict(command=candidate)):
                code, result = self.assistant_send(room, context, "帮我用 SG 降噪", allow_ai=True)
            self.assertEqual(code, 200, result)
            self.assertEqual(result["reply"]["provider"], "local_rules")
            self.assertTrue(result["reply"]["fallback_reason"])
            self.assertNotIn("python", json.dumps(result["reply"]["command"]))

    def test_assistant_model_failure_and_no_key(self):
        room, context = self.assistant_open()
        with patch.object(engine, "assistant_settings", return_value=dict(provider="deepseek", model="mock", configured=False)):
            result = self.assistant_send(room, context, allow_ai=True)[1]
        self.assertEqual(result["reply"]["provider"], "local_rules")
        settings = dict(provider="deepseek", model="mock", configured=True)
        for failure in [HTTPError("https://api.deepseek.com", 402, "balance", {}, None), TimeoutError("timed out")]:
            with patch.object(engine, "assistant_settings", return_value=settings), patch.object(engine, "chat_with_assistant", side_effect=failure):
                code, result = self.assistant_send(room, context, allow_ai=True)
            self.assertEqual(code, 200, result)
            self.assertEqual(result["reply"]["provider"], "local_rules")
            self.assertTrue(result["reply"]["fallback_reason"])

    def test_assistant_hyperspectral_scope_and_tsvd(self):
        room, context = self.assistant_open(surface="hyperspectral")
        result = self.assistant_send(room, context, "只对当前像素进行降噪")[1]
        self.assertFalse(result["reply"]["command"]["requires_confirmation"])
        self.assertIn("整个数据集", result["reply"]["content"])
        settings = dict(provider="deepseek", model="mock", configured=True)
        command = dict(action="process_hyperspectral", scope="dataset", steps=[dict(type="denoise", method="tsvd", params=dict(threshold=0.001))])
        with patch.object(engine, "assistant_settings", return_value=settings), patch.object(engine, "plan_processing_command", return_value=dict(command=command)):
            result = self.assistant_send(room, context, "帮我对整个数据集进行降噪", allow_ai=True)[1]
        self.assertEqual(result["reply"]["command"]["scope"], "dataset")
        self.assertEqual(result["reply"]["command"]["steps"][0]["method"], "tsvd")

    def test_assistant_tools_do_not_execute_commands(self):
        room, context = self.assistant_open(context={}, surface="extra-tools")
        result = self.assistant_send(room, context, "帮我合并文件")[1]
        self.assertFalse(result["reply"]["command"]["requires_confirmation"])
        self.assertIn("没有执行", result["reply"]["content"])

    def test_assistant_clear_and_scoped_concurrency(self):
        room, context = self.assistant_open()
        started, finish = threading.Event(), threading.Event()
        settings = dict(provider="deepseek", model="mock", configured=True)
        def slow(*args):
            started.set()
            finish.wait(5)
            return dict(message="mock reply")
        with patch.object(engine, "assistant_settings", return_value=settings), patch.object(engine, "chat_with_assistant", side_effect=slow):
            thread = threading.Thread(target=lambda: self.assistant_send(room, context, allow_ai=True))
            thread.start()
            self.assertTrue(started.wait(3))
            try:
                self.assertEqual(self.assistant_send(room, context)[0], 429)
                self.assertEqual(self.call("/api/assistant/conversations/" + room["id"], method="DELETE")[0], 409)
            finally:
                finish.set()
                thread.join(5)
        self.assertEqual(self.call("/api/assistant/conversations/" + room["id"], method="DELETE")[0], 200)
        self.assertEqual(self.assistant_open(context)[0]["messages"], [])

    def test_assistant_ollama_optional(self):
        with patch.dict(engine.os.environ, {"RAMANCLOUD_ASSISTANT_PROVIDER": "ollama", "OLLAMA_BASE_URL": "http://127.0.0.1:11434"}):
            self.assertEqual(engine.assistant_settings()["provider"], "ollama")
            with patch.object(workflow, "urlopen", return_value=io.BytesIO(b'{"message":{"content":"local model reply"}}')) as request:
                answer = engine._call_model([dict(role="user", content="hello")], timeout=10, num_predict=100, stream=False)
                self.assertEqual(answer, "local model reply")
                self.assertIn("/api/chat", request.call_args[0][0].full_url)

    def test_assistant_heatmap_slice_comparison_guard(self):
        context = dict(page="hyperspectral", raw_preview=[[1, 2]], processed_preview=[[2, 3]], preview_wavenumber=500, processed_preview_wavenumber=600)
        self.assertFalse(engine._model_context(context)["preview_comparison"]["available"])
