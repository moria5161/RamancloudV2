"""Real HTTP integration tests, isolated from the user's database and uploads."""
import io
import gc
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.request import Request, urlopen

import numpy as np

TEMP = tempfile.TemporaryDirectory(prefix="raman-ai-tests-")
for key in list(os.environ):
    if key.startswith("MYSQL_") or key in ("DATABASE_URL", "MYSQL_URL"):
        os.environ.pop(key)
os.environ["RAMANCLOUD_DB_PATH"] = str(Path(TEMP.name) / "test.db")
os.environ["RAMANCLOUD_STORAGE_DIR"] = str(Path(TEMP.name) / "files")
os.environ["RAMANCLOUD_STORAGE_BACKEND"] = "local"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as backend
import ai_workflow as workflow
import uvicorn
from assistant_cases import AssistantCases
from batch_cases import BatchCases
from tshi_cases import TSHICases
from format_cases import FormatCases
from despike_cases import DespikeCases
from collaboration_cases import CollaborationCases
from structure_cases import StructureCases
from library_cases import LibraryCases
from ssnet_cases import SSnetCases
from history_resource_cases import HistoryResourceCases
from qa_assistant_cases import QaAssistantCases
from qa_action_cases import QaActionCases
from feedback_cases import FeedbackCases
from module_record_cases import ModuleRecordCases
from spectrum_export_cases import SpectrumExportCases
from model_history_cases import ModelHistoryCases
from preference_cases import PreferenceCases
from peak_fitting_cases import PeakFittingCases


class WorkflowTests(PeakFittingCases, PreferenceCases, QaActionCases, ModelHistoryCases, SpectrumExportCases, ModuleRecordCases, FeedbackCases, QaAssistantCases, HistoryResourceCases, AssistantCases, BatchCases, TSHICases, FormatCases, DespikeCases, CollaborationCases, StructureCases, LibraryCases, SSnetCases, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        cls.base = "http://127.0.0.1:" + str(sock.getsockname()[1])
        cls.server = uvicorn.Server(uvicorn.Config(backend.app, log_level="error"))
        cls.thread = threading.Thread(target=cls.server.run, kwargs={"sockets": [sock]}, daemon=True)
        cls.thread.start()
        for _ in range(100):
            if cls.server.started:
                break
            time.sleep(0.05)
        if not cls.server.started:
            raise RuntimeError("Test HTTP server did not start")
        cls.auth = cls.request("/api/auth/register", dict(username="ai_test_owner", password="test-password", role="user"))[1]["data"]
        cls.other = cls.request("/api/auth/register", dict(username="ai_test_other", password="test-password", role="user"))[1]["data"]

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(15)
        gc.collect()
        # sqlite connections are managed by the existing app; Windows may defer temp cleanup.
        try:
            TEMP.cleanup()
        except PermissionError:
            pass

    @classmethod
    def request(cls, path, data=None, token=None, method=None, raw=None, content_type=None):
        headers = {}
        if token:
            headers["Authorization"] = "Bearer " + token
        body = raw if raw is not None else json.dumps(data).encode() if data is not None else None
        if body is not None:
            headers["Content-Type"] = content_type or "application/json"
        req = Request(cls.base + path, data=body, headers=headers, method=method or ("POST" if body is not None else "GET"))
        try:
            response = urlopen(req, timeout=20)
        except HTTPError as exc:
            response = exc
        content = response.read()
        if "application/json" in response.headers.get("Content-Type", ""):
            content = json.loads(content)
        return response.code, content

    def call(self, path, data=None, **kwargs):
        return self.request(path, data, token=self.auth["token"], **kwargs)

    def task(self):
        code, value = self.call("/api/ai-workflows/source", {"demo": "tutorial"})
        self.assertEqual(code, 200, value)
        return value

    def plan(self, task, goal="去除背景、适度降噪，保留窄峰", **extra):
        with patch.object(workflow, "config", return_value={"api_key": "", "model": "test", "base_url": "https://api.deepseek.com"}):
            code, value = self.call(f"/api/ai-workflows/{task['id']}/recommend", dict(goal=goal, **extra))
        self.assertEqual(code, 200, value)
        return value["version"]

    def wait_version(self, task, vid):
        for _ in range(100):
            code, value = self.call(f"/api/ai-workflows/{task['id']}/versions/{vid}")
            if value["status"] not in ("queued", "running", "previewing"):
                return value
            time.sleep(0.05)
        self.fail("Execution did not finish")

    def test_auth_and_owner_isolation(self):
        self.assertEqual(self.request("/api/ai-workflows/config")[0], 401)
        task = self.task()
        version = self.plan(task)
        for suffix in ["", f"/versions/{version['id']}", "/download?kind=original"]:
            self.assertEqual(self.request(f"/api/ai-workflows/{task['id']}" + suffix, token=self.other["token"])[0], 404)

    def test_end_to_end_preview_execute_replay_export(self):
        task = self.task()
        version = self.plan(task)
        self.assertEqual(version["provider"], "local_rules")
        self.assertTrue(version["fallback_reason"])
        prefix = f"/api/ai-workflows/{task['id']}/versions/{version['id']}"
        code, preview = self.call(prefix + "/preview", {})
        self.assertEqual(code, 200, preview)
        self.assertEqual(len(preview["preview"]), 2)
        self.assertEqual(self.call(prefix + "/execute", {})[0], 200)
        result = self.wait_version(task, version["id"])
        self.assertEqual(result["status"], "completed", result.get("error"))
        np.testing.assert_allclose(result["trace"][-1]["after"]["intensity"], preview["preview"][-1]["after"]["intensity"])
        history = self.call("/api/analysis-runs/" + result["analysis_run_id"])[1]["data"]["run"]
        self.assertEqual(history["result"]["ai_workflow_id"], task["id"])
        self.assertEqual(self.call(prefix + "/execute", {})[0], 409)
        code, bundle = self.call(f"/api/ai-workflows/{task['id']}/download?version_id={version['id']}")
        self.assertEqual(code, 200)
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            self.assertIn("step_1_airpls.txt", archive.namelist())
            record = json.loads(archive.read("workflow.json"))
            self.assertEqual(record["original"], task["original"])
            self.assertEqual(len(record["version"]["trace"]), 2)
        code, replay = self.call(f"/api/ai-workflows/{task['id']}/versions", dict(goal=version["goal"], steps=version["steps"], parent_id=version["id"]))
        self.assertEqual(code, 200, replay)
        self.call(f"/api/ai-workflows/{task['id']}/versions/{replay['id']}/execute", {})
        repeated = self.wait_version(task, replay["id"])
        np.testing.assert_allclose(repeated["trace"][-1]["after"]["intensity"], result["trace"][-1]["after"]["intensity"])
        self.assertEqual(self.call(f"/api/ai-workflows/{task['id']}")[1]["original"], task["original"])

    def test_feedback_and_skip_preserve_parent(self):
        task = self.task()
        version = self.plan(task)
        revised = self.plan(task, parent_id=version["id"], feedback="峰变弱了，减小平滑窗口")
        self.assertLess(revised["steps"][-1]["params"]["window_size"], version["steps"][-1]["params"]["window_size"])
        edited = json.loads(json.dumps(version["steps"]))
        edited[0]["enabled"] = False
        code, manual = self.call(f"/api/ai-workflows/{task['id']}/versions", dict(goal=version["goal"], parent_id=version["id"], steps=edited))
        self.assertEqual(code, 200, manual)
        trace = self.call(f"/api/ai-workflows/{task['id']}/versions/{manual['id']}/preview", {})[1]["preview"]
        self.assertEqual(trace[0]["status"], "skipped")
        self.assertEqual(trace[0]["before"]["intensity"], trace[0]["after"]["intensity"])
        old = self.call(f"/api/ai-workflows/{task['id']}/versions/{version['id']}")[1]
        self.assertTrue(old["steps"][0]["enabled"])

    def test_feedback_keeps_manual_baseline_parameters(self):
        task = self.task()
        parent = self.plan(task)
        parent["steps"][0]["params"]["lam"] = 123456
        manual = self.call(f"/api/ai-workflows/{task['id']}/versions", dict(goal=parent["goal"], steps=parent["steps"], parent_id=parent["id"]))[1]
        revised = self.plan(task, parent_id=manual["id"], feedback="峰变弱了，减小平滑窗口，其他步骤不变")
        self.assertEqual(revised["steps"][0]["params"]["lam"], 123456)

    def test_busy_version_cannot_execute_preview_or_delete_twice(self):
        task = self.task()
        plan = self.plan(task)
        started, release = threading.Event(), threading.Event()
        original = backend.apply_pipeline
        def wait_for_release(*args):
            started.set()
            release.wait(5)
            return original(*args)
        path = f"/api/ai-workflows/{task['id']}/versions/{plan['id']}"
        with patch.dict(backend.__dict__, {"apply_pipeline": wait_for_release}):
            try:
                self.assertEqual(self.call(path + "/execute", {})[0], 200)
                self.assertTrue(started.wait(3))
                self.assertEqual(self.call(path + "/execute", {})[0], 409)
                self.assertEqual(self.call(path + "/preview", {})[0], 409)
                self.assertEqual(self.call(f"/api/ai-workflows/{task['id']}", method="DELETE")[0], 409)
            finally:
                release.set()
            result = self.wait_version(task, plan["id"])
        self.assertEqual(result["status"], "completed")

    def test_provider_timeout_and_forbidden_operations_fall_back(self):
        task = self.task()
        parent = self.plan(task)
        settings = dict(api_key="private", model="test", base_url="https://api.deepseek.com")
        path = f"/api/ai-workflows/{task['id']}/recommend"
        with patch.object(workflow, "config", return_value=settings), patch.object(workflow, "call_chat_model", side_effect=URLError("test")):
            result = self.call(path, dict(goal=parent["goal"], allow_ai=True))[1]
            self.assertIn("超时", result["version"]["fallback_reason"])
        with patch.object(workflow, "config", return_value=settings), patch.object(workflow, "call_chat_model", return_value=dict(summary="bad", steps=parent["steps"])):
            result = self.call(path, dict(goal="不要去基线，仅降噪", allow_ai=True))[1]
            self.assertEqual(result["version"]["provider"], "local_rules")
            self.assertEqual([step["type"] for step in result["version"]["steps"]], ["denoise"])

    def test_deepseek_http_contract(self):
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit):
                return json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": '{"summary":"ok","steps":[]}'}}]}).encode()
        with patch.object(workflow, "urlopen", return_value=FakeResponse()) as http:
            result = workflow.call_chat_model(dict(api_key="test-only", base_url="https://api.deepseek.com", model="deepseek-flash"), dict(goal="降噪"))
            request = http.call_args[0][0]
            payload = json.loads(request.data)
            self.assertEqual(request.full_url, "https://api.deepseek.com/chat/completions")
            self.assertEqual(request.get_header("Authorization"), "Bearer test-only")
            self.assertEqual(payload["response_format"], {"type": "json_object"})
            self.assertEqual(payload["thinking"], {"type": "disabled"})
            self.assertEqual(result["summary"], "ok")
        with self.assertRaises(ValueError):
            workflow.call_chat_model(dict(api_key="x", base_url="http://insecure", model="test"), {})

    def test_ollama_default_and_no_cloud_credentials(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(Path, "exists", return_value=False):
            settings = workflow.config()
            self.assertEqual(settings["provider"], "ollama")
            self.assertEqual(settings["model"], "qwen3:4b-instruct-2507-q4_K_M")
            self.assertTrue(workflow.model_configured(settings))
        old = json.dumps(dict(provider="deepseek", api_key="private", model="deepseek-flash"))
        with patch.dict(os.environ, {"RAMANCLOUD_AI_PROVIDER": "ollama", "RAMANCLOUD_AI_API_KEY": "never-send", "DEEPSEEK_API_KEY": "never-send"}, clear=True), patch.object(Path, "exists", return_value=True), patch.object(Path, "read_text", return_value=old):
            settings = workflow.config()
            self.assertEqual(settings["api_key"], "")
            self.assertEqual(settings["base_url"], "http://127.0.0.1:11434")

    def test_ollama_json_contract_and_security(self):
        settings = dict(provider="ollama", base_url="http://127.0.0.1:11434", model="qwen3:4b", api_key="must-not-send")
        response = json.dumps(dict(message=dict(content=json.dumps(dict(summary="ok"))), done_reason="stop")).encode()
        with patch.object(workflow, "urlopen", return_value=io.BytesIO(response)) as http:
            self.assertEqual(workflow.call_chat_model(settings, dict(goal="降噪"))["summary"], "ok")
            request = http.call_args[0][0]
            payload = json.loads(request.data)
            self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
            self.assertIsNone(request.get_header("Authorization"))
            self.assertEqual(payload["format"], workflow.plan_schema())
            self.assertFalse(payload["think"])
            self.assertTrue(payload["messages"][-1]["content"].endswith('/no_think'))
            self.assertTrue(payload["stream"])
            self.assertGreaterEqual(http.call_args[1]["timeout"], 180)
        for changes in [dict(base_url="http://example.com"), dict(base_url="https://ollama.com"), dict(base_url="http://secret@localhost:11434"), dict(base_url="http://localhost:11434/path"), dict(model="qwen3:4b-cloud")]:
            with patch.object(workflow, "urlopen") as http, self.assertRaises(workflow.AIConfigurationError):
                workflow.call_chat_model(dict(settings, **changes), {})
            http.assert_not_called()

    def test_ollama_availability(self):
        settings = dict(provider="ollama", base_url="http://127.0.0.1:11434", model="qwen3:4b")
        for content, available, state in [(b'{"models":[{"name":"qwen3:4b"}]}', True, "ready"), (b'{"models":[]}', False, "model_missing")]:
            with patch.object(workflow, "urlopen", return_value=io.BytesIO(content)):
                self.assertEqual(workflow.model_availability(settings), dict(available=available, availability=state))
        with patch.object(workflow, "urlopen", side_effect=URLError("offline")):
            self.assertEqual(workflow.model_availability(settings)["availability"], "offline")

    def test_ollama_instruct_does_not_request_thinking_or_expose_it(self):
        settings = dict(provider="ollama", base_url="http://127.0.0.1:11434", model="qwen3:4b-instruct-2507-q4_K_M")
        for raw in ["final answer", "<think>private reasoning</think>final answer", "private reasoning</think>final answer"]:
            response = io.BytesIO(json.dumps(dict(message=dict(content=raw))).encode())
            with patch.object(workflow, "urlopen", return_value=response) as http:
                self.assertEqual(workflow.call_chat_completion(settings, [dict(role="user", content="hello")]), "final answer")
                payload = json.loads(http.call_args[0][0].data)
                self.assertNotIn("think", payload)
                self.assertEqual(payload["messages"][-1]["content"], "hello")
        response = io.BytesIO(json.dumps(dict(message=dict(content="<think>unfinished reasoning"))).encode())
        with patch.object(workflow, "urlopen", return_value=response), self.assertRaises(ValueError):
            workflow.call_chat_completion(settings, [])

    def test_ollama_stream_accepts_complete_json_and_rejects_incomplete(self):
        settings = dict(provider="ollama", base_url="http://127.0.0.1:11434", model="qwen3:4b")
        def stream(parts):
            return io.BytesIO(b"\n".join(json.dumps(dict(message=dict(content=value))).encode() for value in parts))
        response = stream(['{"summary":', '"ok"}', 'trailing output must not be consumed'])
        with patch.object(workflow, "urlopen", return_value=response):
            result = workflow.call_chat_completion(settings, [dict(role="user", content="JSON")], json_mode=True)
            self.assertEqual(json.loads(result), dict(summary="ok"))
        for parts in [['{"summary":'], [" "]]:
            with patch.object(workflow, "urlopen", return_value=stream(parts)), self.assertRaises(ValueError):
                workflow.call_chat_completion(settings, [], json_mode=True)

    def test_ollama_recommend_without_key_and_failure_fallback(self):
        task = self.task()
        plan = self.plan(task)
        settings = dict(provider="ollama", provider_name="Ollama", api_key="", model="qwen3:4b")
        path = f"/api/ai-workflows/{task['id']}/recommend"
        with patch.object(workflow, "config", return_value=settings), patch.object(workflow, "call_chat_model", return_value=dict(summary="本地模型方案", steps=plan["steps"])):
            result = self.call(path, dict(goal=plan["goal"], allow_ai=True))[1]["version"]
            self.assertEqual(result["provider"], "ollama:qwen3:4b")
        with patch.object(workflow, "config", return_value=settings), patch.object(workflow, "call_chat_model", side_effect=URLError("offline")):
            result = self.call(path, dict(goal=plan["goal"], allow_ai=True))[1]["version"]
            self.assertEqual(result["provider"], "local_rules")
            self.assertIn("Ollama", result["fallback_reason"])
        with patch.object(workflow, "config", return_value=settings), patch.object(workflow, "call_chat_model") as model:
            self.call(path, dict(goal=plan["goal"], allow_ai=False))
            model.assert_not_called()

    def test_import_history_for_intelligent_analysis(self):
        task = self.task()
        version = self.plan(task)
        self.call(f"/api/ai-workflows/{task['id']}/versions/{version['id']}/execute", {})
        result = self.wait_version(task, version["id"])
        payload = dict(history_run_id=result["analysis_run_id"])
        code, imported = self.call("/api/ai-workflows/source", payload)
        self.assertEqual(code, 200, imported)
        self.assertEqual(imported["original"], task["original"])
        fields = ("type", "method", "params", "enabled")
        self.assertEqual([{key: step[key] for key in fields} for step in imported["versions"][0]["steps"]],
                         [{key: step[key] for key in fields} for step in version["steps"]])
        self.assertEqual(imported["versions"][0]["status"], "draft")
        self.assertEqual(self.request("/api/ai-workflows/source", payload, token=self.other["token"])[0], 404)

    def test_document_source_validation_and_original_checksum(self):
        import hashlib
        content = b'wave,intensity,other\n' + b'\n'.join(f'{i},{i + 10},{i * i}'.encode() for i in range(30))
        original = backend.read_spectrum_with_metadata(content)
        self.assertEqual(original[2]["numeric_columns"], 3)
        self.assertEqual(original[2]["intensity_column"], 2)
        np.testing.assert_array_equal(original[1], np.arange(30) + 10)
        self.assertEqual(original[2]["ignored_lines"], 1)
        bom_wave, bom_intensity, _ = backend.read_spectrum_with_metadata(b'\xef\xbb\xbf' + content)
        np.testing.assert_array_equal(bom_wave, original[0])
        np.testing.assert_array_equal(bom_intensity, original[1])
        _, _, gaps = backend.read_spectrum_with_metadata(b'1,,10\n2,,20\n3,,30')
        self.assertEqual(gaps['wavenumber_column'], 1)
        self.assertEqual(gaps['intensity_column'], 3)
        boundary = "source-check-boundary"
        def upload(name):
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="confirm_conversion"\r\n\r\ntrue\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: text/plain\r\n\r\n'.encode() + content + f'\r\n--{boundary}--\r\n'.encode())
            return self.call('/api/ai-workflows/upload', raw=body, content_type='multipart/form-data; boundary=' + boundary)
        code, task = upload('sample.csv')
        self.assertEqual(code, 200, task)
        info = task['diagnostics']['source_check']
        self.assertEqual(info['sha256'], hashlib.sha256(content).hexdigest())
        self.assertTrue(info['original_preserved'])
        self.assertEqual(self.call(f"/api/ai-workflows/{task['id']}/download?kind=original")[1], content)
        self.assertEqual(upload('sample.xlsx')[0], 400)

    def test_document_preprocess_region_candidates_and_confirmation(self):
        task = self.task()
        endpoint = f"/api/ai-workflows/{task['id']}/recommend"
        body = dict(goal='默认预处理', phase='preprocess', region=dict(start=400, end=1800), compare_candidates=True)
        with patch.object(workflow, 'call_chat_model') as model:
            code, response = self.call(endpoint, body)
            model.assert_not_called()
        self.assertEqual(code, 200, response)
        version = response['version']
        self.assertEqual(version['status'], 'draft')
        self.assertEqual(version['metadata']['phase'], 'preprocess')
        self.assertEqual(version['steps'][0]['params'], dict(start=400., end=1800.))
        self.assertEqual(len(version['metadata']['candidates']), 3)
        self.assertEqual(version['metadata']['evaluation_method'], 'heuristic')
        self.assertIsNone(version['analysis_run_id'])
        for candidate in version['metadata']['candidates']:
            if candidate['status'] == 'valid':
                self.assertTrue(np.isfinite(candidate['score']))
                self.assertLessEqual(len(candidate['curves']['wavenumber']), 256)
                self.assertGreater(candidate['points'], 8)
        other_candidate = next(item for item in version['metadata']['candidates'] if item['status'] == 'valid' and item['id'] != version['metadata']['selected_candidate'])
        url = f"/api/ai-workflows/{task['id']}/versions/{version['id']}/candidates/{other_candidate['id']}"
        chosen = self.call(url, {})[1]
        self.assertNotEqual(chosen['id'], version['id'])
        self.assertEqual(chosen['parent_id'], version['id'])
        self.assertEqual(chosen['metadata']['selected_candidate'], other_candidate['id'])
        self.assertEqual(self.request(url, {}, token=self.other['token'])[0], 404)
        self.assertEqual(self.call(f"/api/ai-workflows/{task['id']}/versions/{version['id']}")[1]['metadata']['selected_candidate'], version['metadata']['selected_candidate'])
        self.call(f"/api/ai-workflows/{task['id']}/versions/{chosen['id']}/execute", {})
        finished = self.wait_version(task, chosen['id'])
        self.assertEqual(finished['status'], 'completed', finished.get('error'))
        self.assertGreaterEqual(min(finished['trace'][-1]['after']['wavenumber']), 400)
        self.assertLessEqual(max(finished['trace'][-1]['after']['wavenumber']), 1800)

    def test_document_bad_range_is_rejected_before_model(self):
        task = self.task()
        endpoint = f"/api/ai-workflows/{task['id']}/recommend"
        with patch.object(workflow, 'call_chat_model') as model:
            for region in [dict(start=0, end=900), dict(start=900, end=800), dict(start=500, end=501), dict(start=100, end=5000)]:
                self.assertEqual(self.call(endpoint, dict(goal='降噪', region=region, allow_ai=True))[0], 400)
            self.assertEqual(self.call(endpoint, dict(goal='不要裁剪，仅降噪', region=dict(start=400, end=1800), allow_ai=True))[0], 400)
            model.assert_not_called()

    def test_document_refinement_requires_completed_preprocessing(self):
        task = self.task()
        endpoint = f"/api/ai-workflows/{task['id']}/recommend"
        self.assertEqual(self.call(endpoint, dict(goal='适度降噪', phase='refine'))[0], 400)
        version = self.call(endpoint, dict(goal='默认预处理', phase='preprocess'))[1]['version']
        self.assertEqual(self.call(endpoint, dict(goal='适度降噪', phase='refine', parent_id=version['id']))[0], 400)
        self.call(f"/api/ai-workflows/{task['id']}/versions/{version['id']}/execute", {})
        finished = self.wait_version(task, version['id'])
        self.assertEqual(finished['status'], 'completed')
        refined = self.call(endpoint, dict(goal='适度降噪，保留主要峰', phase='refine', parent_id=version['id']))[1]['version']
        self.assertEqual(refined['metadata']['phase'], 'refine')
        self.assertEqual(self.call(f"/api/ai-workflows/{task['id']}/versions/{version['id']}")[1]['trace'], finished['trace'])

    def test_document_reuses_only_unchanged_prefix_and_replays_fully(self):
        task = self.task()
        version = self.call(f"/api/ai-workflows/{task['id']}/recommend", dict(goal='默认预处理', phase='preprocess', region=dict(start=400, end=1800)))[1]['version']
        self.call(f"/api/ai-workflows/{task['id']}/versions/{version['id']}/execute", {})
        completed = self.wait_version(task, version['id'])
        steps = json.loads(json.dumps(completed['steps']))
        changed_index = next(i for i, step in enumerate(steps) if step['method'] == 'sg')
        steps[changed_index]['params']['window_size'] += 2
        steps[0]['reason'] = 'Changed explanation does not change numeric computation.'
        edited = self.call(f"/api/ai-workflows/{task['id']}/versions", dict(goal=version['goal'], steps=steps, parent_id=version['id']))[1]
        original = backend.apply_pipeline
        with patch.dict(backend.__dict__, {'apply_pipeline': unittest.mock.Mock(wraps=original)}) as patched:
            preview = self.call(f"/api/ai-workflows/{task['id']}/versions/{edited['id']}/preview", {})[1]
            self.assertEqual(patched['apply_pipeline'].call_count, len(steps) - changed_index)
        self.assertEqual(preview['reused_steps'], changed_index)
        self.assertEqual([record['reused'] for record in preview['preview']], [i < changed_index for i in range(len(steps))])
        self.assertEqual(preview['preview'][0]['reused_from_version_id'], version['id'])
        expected = original(np.asarray(task['original']['wavenumber']), np.asarray(task['original']['intensity']), [backend.Step(type=s['type'], method=s['method'], params=s['params']) for s in steps])[1]
        np.testing.assert_allclose(preview['preview'][-1]['after']['intensity'], expected)
        self.assertEqual(self.call(f"/api/ai-workflows/{task['id']}/versions/{version['id']}")[1]['trace'], completed['trace'])
        with patch.dict(backend.__dict__, {'apply_pipeline': unittest.mock.Mock(wraps=original)}) as patched:
            self.call(f"/api/ai-workflows/{task['id']}/versions/{edited['id']}/execute", dict(recompute_all=True))
            replay = self.wait_version(task, edited['id'])
            self.assertEqual(patched['apply_pipeline'].call_count, len(steps))
        self.assertEqual(replay['reused_steps'], 0)

    def test_document_deleting_task_removes_candidate_metadata(self):
        task = self.task()
        version = self.call(f"/api/ai-workflows/{task['id']}/recommend", dict(goal='默认预处理', phase='preprocess', compare_candidates=True))[1]['version']
        self.assertEqual(self.call(f"/api/ai-workflows/{task['id']}", method='DELETE')[0], 200)
        with backend.db_connect() as conn:
            self.assertIsNone(conn.execute('SELECT version_id FROM ai_plan_metadata WHERE version_id = ?', (version['id'],)).fetchone())

    def test_document_reuse_stops_at_crop_skip_or_order_change(self):
        task = self.task()
        version = self.call(f"/api/ai-workflows/{task['id']}/recommend", dict(goal='默认预处理', phase='preprocess', region=dict(start=400, end=1800)))[1]['version']
        parent = self.call(f"/api/ai-workflows/{task['id']}/versions/{version['id']}/preview", {})[1]
        for kind, expected in [('crop', 0), ('skip', 1), ('order', 2)]:
            with self.subTest(change=kind):
                steps = json.loads(json.dumps(parent['steps']))
                if kind == 'crop':
                    steps[0]['params']['start'] = 500
                elif kind == 'skip':
                    steps[1]['enabled'] = False
                else:
                    steps[-2], steps[-1] = steps[-1], steps[-2]
                child = self.call(f"/api/ai-workflows/{task['id']}/versions", dict(goal=version['goal'], steps=steps, parent_id=parent['id']))[1]
                result = self.call(f"/api/ai-workflows/{task['id']}/versions/{child['id']}/preview", {})[1]
                self.assertEqual(result['reused_steps'], expected)
                self.assertTrue(all(not row['reused'] for row in result['preview'][expected:]))

    def test_document_model_receives_only_selected_band_and_whitelisted_plan(self):
        task = self.task()
        default = self.plan(task)
        settings = dict(provider='ollama', model='mock-local', api_key='')
        with patch.object(workflow, 'config', return_value=settings), patch.object(workflow, 'call_chat_model', return_value=dict(summary='Local model', steps=default['steps'])) as model:
            code, result = self.call(f"/api/ai-workflows/{task['id']}/recommend", dict(goal='默认预处理', phase='preprocess', region=dict(start=400, end=1800), allow_ai=True))
            self.assertEqual(code, 200, result)
            context = model.call_args[0][1]
            self.assertEqual(context['phase'], 'preprocess')
            self.assertEqual(context['selected_region'], dict(start=400, end=1800))
            self.assertLessEqual(len(context['sample']), 640)
            self.assertEqual(context['spectral_data']['axis_unit'], 'cm^-1')
            self.assertEqual(context['spectral_data']['transmitted_points'], len(context['sample']))
            self.assertTrue(all(400 <= point[0] <= 1800 for point in context['sample']))
            self.assertNotIn('user', context)
            self.assertEqual(result['version']['provider'], 'ollama:mock-local')
            self.assertEqual(result['version']['steps'][0]['params'], dict(start=400, end=1800))

    def test_preprocess_model_selects_custom_algorithm_parameters_and_local_never_calls_model(self):
        task=self.task();path=f"/api/ai-workflows/{task['id']}/recommend"
        settings=dict(provider='ollama',model='mock-local',api_key='')
        proposal=dict(summary='依据噪声特征选择小波',steps=[dict(type='denoise',method='wtd',params=dict(wavelet='db2',level=2),reason='降低噪声，保留窄峰')])
        with patch.object(workflow,'config',return_value=settings),patch.object(workflow,'call_chat_model',return_value=proposal) as model:
            code,result=self.call(path,dict(goal='默认预处理',phase='preprocess',allow_ai=False))
            self.assertEqual(code,200,result);model.assert_not_called()
            self.assertEqual(result['version']['provider'],'local_rules')
            code,result=self.call(path,dict(goal='默认预处理',phase='preprocess',allow_ai=True))
            self.assertEqual(code,200,result);model.assert_called_once()
            step=next(s for s in result['version']['steps'] if s['method']=='wtd')
            self.assertEqual(step['params'],dict(wavelet='db2',level=2))
            self.assertEqual(result['version']['metadata']['recommendation_mode'],'model')
            self.assertGreater(result['version']['metadata']['model_input']['transmitted_points'],96)

    def test_model_success_invalid_output_and_consent(self):
        task = self.task()
        plan = self.plan(task)
        settings = dict(api_key="test-secret", model="mock-model", base_url="https://api.deepseek.com")
        with patch.object(workflow, "config", return_value=settings), patch.object(workflow, "call_chat_model", return_value=dict(summary="模型方案", clarification="", steps=plan["steps"])) as provider:
            code, result = self.call(f"/api/ai-workflows/{task['id']}/recommend", dict(goal=plan["goal"], allow_ai=True))
            self.assertEqual(code, 200, result)
            self.assertEqual(result["version"]["provider"], "deepseek:mock-model")
            self.assertLessEqual(len(provider.call_args[0][1]["sample"]), 640)
            self.assertGreater(len(provider.call_args[0][1]["sample"]), 96)
            self.assertNotIn("test-secret", json.dumps(result))
        for bad in [{"summary": "bad", "steps": [{"type": "code", "method": "eval"}]}, {}, {"summary": "bad", "steps": [{"type": "cut", "method": "cut", "params": {"start": 100, "end": 200}}]}]:
            with patch.object(workflow, "config", return_value=settings), patch.object(workflow, "call_chat_model", return_value=bad):
                result = self.call(f"/api/ai-workflows/{task['id']}/recommend", dict(goal=plan["goal"], allow_ai=True))[1]
                self.assertEqual(result["version"]["provider"], "local_rules")
                self.assertIn("未通过", result["version"]["fallback_reason"])
        with patch.object(workflow, "config", return_value=settings), patch.object(workflow, "call_chat_model") as provider:
            result = self.call(f"/api/ai-workflows/{task['id']}/recommend", dict(goal=plan["goal"], allow_ai=False))[1]
            provider.assert_not_called()
            self.assertIn("已选择本地规则", result["version"]["fallback_reason"])

    def test_invalid_and_ambiguous_plans(self):
        task = self.task()
        with patch.object(workflow, "config", return_value=dict(api_key="", model="test")):
            value = self.call(f"/api/ai-workflows/{task['id']}/recommend", dict(goal="看看数据"))[1]
            self.assertTrue(value["clarification"])
        for steps in [[], [{"type": "normalize", "method": "sg"}], [{"type": "denoise", "method": "sg", "params": {"window_size": 6}}], [{"type": "denoise", "method": "sg", "params": {"unexpected": 3}}], [{"type": "cut", "method": "cut", "params": {"start": -100, "end": -90}}]]:
            self.assertEqual(self.call(f"/api/ai-workflows/{task['id']}/versions", dict(goal="降噪", steps=steps))[0], 400)
        stranger = self.task()
        foreign = self.plan(stranger)
        self.assertEqual(self.call(f"/api/ai-workflows/{task['id']}/versions", dict(goal="降噪", steps=foreign["steps"], parent_id=foreign["id"]))[0], 404)

    def test_siliconflow_http_contract_and_paid_model_block(self):
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit):
                return json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": '{"summary":"ok","steps":[]}'}}]}).encode()
        settings = dict(provider="siliconflow", api_key="fake-siliconflow-key", base_url="https://api.siliconflow.cn/v1", model="Qwen/Qwen3-8B")
        with patch.object(workflow, "urlopen", return_value=FakeResponse()) as http:
            workflow.call_chat_model(settings, dict(goal="降噪"))
            request = http.call_args[0][0]
            payload = json.loads(request.data)
            self.assertEqual(request.full_url, "https://api.siliconflow.cn/v1/chat/completions")
            self.assertEqual(request.get_header("Authorization"), "Bearer fake-siliconflow-key")
            self.assertFalse(payload["enable_thinking"])
            self.assertNotIn("thinking", payload)
            self.assertEqual(payload["response_format"], {"type": "json_object"})
        for changes in [dict(model="Pro/Qwen/Qwen3-8B"), dict(base_url="https://api.deepseek.com")]:
            with patch.object(workflow, "urlopen") as http, self.assertRaises(workflow.AIConfigurationError):
                workflow.call_chat_model(dict(settings, **changes), {})
            http.assert_not_called()

    def test_switch_does_not_reuse_deepseek_credentials(self):
        old = json.dumps(dict(api_key="private-old-deepseek-key", base_url="https://api.deepseek.com", model="deepseek-flash"))
        with patch.dict(os.environ, {"RAMANCLOUD_AI_PROVIDER": "siliconflow", "DEEPSEEK_API_KEY": "private-env-deepseek-key"}, clear=True), patch.object(Path, "exists", return_value=True), patch.object(Path, "read_text", return_value=old):
            settings = workflow.config()
            self.assertEqual(settings["provider"], "siliconflow")
            self.assertEqual(settings["api_key"], "")
            self.assertEqual(settings["base_url"], "https://api.siliconflow.cn/v1")
            self.assertEqual(settings["model"], "Qwen/Qwen3-8B")
        new = json.dumps(dict(provider="siliconflow", api_key="new-sf-key"))
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "old-env-key"}, clear=True), patch.object(Path, "exists", return_value=True), patch.object(Path, "read_text", return_value=new):
            self.assertEqual(workflow.config()["api_key"], "new-sf-key")
        with patch.dict(os.environ, {}, clear=True), patch.object(Path, "exists", return_value=True), patch.object(Path, "read_text", return_value=old):
            self.assertEqual(workflow.config()["api_key"], "private-old-deepseek-key")

    def test_siliconflow_history_and_limit_error_labels(self):
        task = self.task()
        plan = self.plan(task)
        settings = dict(provider="siliconflow", provider_name="硅基流动", api_key="fake-key", model="Qwen/Qwen3-8B", base_url="https://api.siliconflow.cn/v1")
        endpoint = f"/api/ai-workflows/{task['id']}/recommend"
        with patch.object(workflow, "config", return_value=settings), patch.object(workflow, "call_chat_model", return_value=dict(summary="模型方案", steps=plan["steps"])):
            version = self.call(endpoint, dict(goal=plan["goal"], allow_ai=True))[1]["version"]
            self.assertEqual(version["provider"], "siliconflow:Qwen/Qwen3-8B")
        for code, label in [(401, "密钥"), (403, "实名认证"), (429, "限流"), (402, "免费型号")]:
            with patch.object(workflow, "config", return_value=settings), patch.object(workflow, "call_chat_model", side_effect=HTTPError("https://api.siliconflow.cn/v1/chat/completions", code, "test", {}, None)):
                result = self.call(endpoint, dict(goal=plan["goal"], allow_ai=True))[1]["version"]
                self.assertEqual(result["provider"], "local_rules")
                self.assertIn(label, result["fallback_reason"])

    def test_numeric_input_validation(self):
        x = np.arange(30.)
        for wave, y in [(x, np.full(30, np.nan)), ([1, 1, 2, 3, 4, 5, 6, 7], np.arange(8)), (x, np.arange(3)), ([1, 3, 2, 4, 5, 6, 7, 8], np.arange(8))]:
            with self.assertRaises(ValueError):
                workflow.validate_spectrum(wave, y)
        workflow.validate_spectrum(x[::-1], np.arange(30.))

    def test_upload_original_bytes_and_project_permissions(self):
        content = b"wave,intensity\n" + b"\n".join(f"{i},{i*i}".encode() for i in range(30))
        boundary = "raman-test-boundary"
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="sample.csv"\r\nContent-Type: text/csv\r\n\r\n'.encode() + content + f"\r\n--{boundary}--\r\n".encode())
        code, task = self.call("/api/ai-workflows/upload", raw=body, content_type="multipart/form-data; boundary=" + boundary)
        self.assertEqual(code, 200, task)
        self.assertEqual(self.call(f"/api/ai-workflows/{task['id']}/download?kind=original")[1], content)
        project = self.call("/api/projects", dict(name="test project"))[1]["data"]["project"]
        form = body.replace(b'name="file"', b'name="files"')
        dataset = self.call(f"/api/projects/{project['id']}/datasets/upload", raw=form, content_type="multipart/form-data; boundary=" + boundary)[1]["data"]["datasets"][0]
        self.assertEqual(self.request("/api/ai-workflows/source", dict(dataset_id=dataset["id"]), token=self.other["token"])[0], 404)
        imported = self.call("/api/ai-workflows/source", dict(dataset_id=dataset["id"]))[1]
        self.assertEqual(imported["project_id"], project["id"])
        self.assertEqual(imported["original"], task["original"])

    def test_execution_failure_keeps_intermediates(self):
        task = self.task()
        plan = self.plan(task)
        original = backend.apply_pipeline
        count = 0
        def fail_second(*args):
            nonlocal count
            count += 1
            if count == 2:
                raise ValueError("injected failure")
            return original(*args)
        with patch.dict(backend.__dict__, {"apply_pipeline": fail_second}):
            self.call(f"/api/ai-workflows/{task['id']}/versions/{plan['id']}/execute", {})
            result = self.wait_version(task, plan["id"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["trace"]), 1)
        self.assertIsNone(result["analysis_run_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
