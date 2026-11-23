import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qa_stream
import llm_runtime

SETTINGS = dict(provider='ollama', model='qwen3:test', base_url='http://127.0.0.1:11434')


class ModelTransportTests(unittest.TestCase):
    def test_axis_default_is_explicit_and_does_not_overwrite_declared_units(self):
        raw = dict(axis_unit='cm^-1 (not declared)', warnings=['文件未声明轴单位，请确认横轴。'])
        result = llm_runtime.axis_reference(raw)
        self.assertEqual(result['axis_unit_basis'], 'platform_default')
        self.assertIn('默认', result['warnings'][0])
        self.assertEqual(raw['axis_unit'], 'cm^-1 (not declared)')
        for unit in ['nm', 'pixel', 'cm^-1', 'eV']:
            self.assertEqual(llm_runtime.axis_reference(dict(axis_unit=unit))['axis_unit'], unit)

    def response(self, *items):
        return io.BytesIO(b''.join(json.dumps(i, ensure_ascii=False).encode() + b'\n' for i in items))

    def test_final_token_is_preserved_before_length_notice_and_slot_released(self):
        with patch.object(qa_stream, 'urlopen', return_value=self.response(
                dict(message=dict(content='已生成')), dict(message=dict(content='最后几个字'), done=True, done_reason='length'))) as upstream:
            stream = qa_stream.tokens(SETTINGS, [dict(role='user', content='解释拉曼光谱')])
            self.assertEqual(next(stream), '已生成')
            self.assertEqual(next(stream), '最后几个字')
            with self.assertRaises(qa_stream.ResponseTruncated): next(stream)
        payload = json.loads(upstream.call_args[0][0].data)
        self.assertEqual(payload['keep_alive'], '15m')
        self.assertEqual(payload['options']['num_predict'], 650)
        self.assertFalse(payload['think'])
        self.assertTrue(llm_runtime._LOCAL.acquire(blocking=False))
        llm_runtime._LOCAL.release()

    def test_network_eof_stays_an_error_and_detailed_request_keeps_larger_budget(self):
        with patch.object(qa_stream, 'urlopen', return_value=self.response(dict(message=dict(content='一部分')))) as upstream:
            with self.assertRaisesRegex(ValueError, 'incomplete'): list(qa_stream.tokens(SETTINGS, [dict(role='user', content='详细解释')]))
        self.assertEqual(json.loads(upstream.call_args[0][0].data)['options']['num_predict'], 1400)

    def test_reference_sampling_preserves_metrics_and_marks_omissions(self):
        full = dict(status='completed', rmse_change=1.2, steps=[dict(method='sg', params=dict(window_size=7))], samples=[[i,i+1] for i in range(96)])
        summary = llm_runtime.compact_reference(full)
        self.assertEqual(summary['status'], 'completed')
        self.assertEqual(summary['rmse_change'], 1.2)
        self.assertEqual(summary['steps'], full['steps'])
        self.assertEqual(summary['samples']['total_items'], 96)
        self.assertEqual(summary['samples']['sampled_items'][0], [0,1])
        self.assertEqual(summary['samples']['sampled_items'][-1], [95,96])
        self.assertEqual(len(full['samples']), 96)
        self.assertLess(len(json.dumps(summary)), len(json.dumps(full)))

    def test_local_inference_lock_releases_after_failure(self):
        with self.assertRaises(ValueError):
            with llm_runtime.inference_slot(SETTINGS): raise ValueError('test')
        self.assertTrue(llm_runtime._LOCAL.acquire(blocking=False))
        llm_runtime._LOCAL.release()
