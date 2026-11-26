"""Bounded local Ollama token stream; no model downloads or execution tools."""
import json
import logging
import os
import time
from urllib.request import Request, urlopen
import ai_workflow as workflow
from llm_runtime import inference_slot, ollama_context_length
LOG = logging.getLogger(__name__)


class ResponseTruncated(ValueError):
    """The model reached its token budget; the emitted text remains usable."""


def tokens(settings, messages):
    if settings.get('provider') != 'ollama':
        # Other configured providers retain the existing validated transport.
        yield workflow.call_chat_completion(settings, messages, max_tokens=1400, timeout=45)
        return
    question = messages[-1].get('content', '').split('\n以下仅为')[0]
    detailed = any(word in question for word in ('详细', '完整报告', '逐行', 'detail', '完整代码'))
    payload = dict(model=settings['model'], messages=messages, stream=True, keep_alive=os.getenv('OLLAMA_KEEP_ALIVE', '15m'),
                   options=dict(temperature=0.2, num_ctx=ollama_context_length(), num_predict=1400 if detailed else 650))
    if settings['model'].lower().startswith('qwen3:'):
        payload['think'] = False
    request = Request(workflow.ollama_base(settings) + '/api/chat', data=json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'})
    size, seen, done = 0, False, False
    with inference_slot(settings), urlopen(request, timeout=300) as response:
        start = time.monotonic()
        for line in response:
            size += len(line)
            if time.monotonic() - start > 300:
                raise TimeoutError('generation deadline')
            if size > 4 * 1024 * 1024:
                raise ValueError('stream limit')
            item = json.loads(line)
            if item.get('error'):
                raise ValueError('upstream error')
            content = item.get('message', {}).get('content', '')
            if content:
                seen = True
                yield content
            if item.get('done'):
                LOG.info('Ollama QA finished: prompt_tokens=%s output_tokens=%s load_ms=%.0f prompt_ms=%.0f generation_ms=%.0f reason=%s',
                         item.get('prompt_eval_count'), item.get('eval_count'), item.get('load_duration',0)/1e6,
                         item.get('prompt_eval_duration',0)/1e6, item.get('eval_duration',0)/1e6, item.get('done_reason','unknown'))
                if item.get('done_reason') == 'length':
                    raise ResponseTruncated('回答达到长度上限，可继续回答。')
                done = True
                break
    if not seen or not done:
        raise ValueError('incomplete response')
