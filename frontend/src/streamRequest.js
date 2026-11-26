import { localize, systemText } from './locale.js';

export async function readNDJSON(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  const readLine = line => {
    if (!line.trim()) return;
    const event = JSON.parse(line);
    if (event.type === 'error') throw new Error(systemText(event.message));
    onEvent(event);
  };
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let end;
      while ((end = buffer.indexOf('\n')) >= 0) {
        readLine(buffer.slice(0, end));
        buffer = buffer.slice(end + 1);
      }
    }
    readLine(buffer + decoder.decode());
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export async function streamRequest(url, options, onRunning) {
  const response = await fetch(`${url}?stream=true`, { ...options, method: 'POST' });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(systemText(typeof body.detail === 'string' ? body.detail : localize('请求失败')));
  }
  let result;
  await readNDJSON(response, event => {
    if (event.type === 'result') result = event.data;
    else if (event.type === 'running') onRunning?.();
  });
  if (result === undefined) throw new Error(localize('请求中断，请重试。'));
  return result;
}
