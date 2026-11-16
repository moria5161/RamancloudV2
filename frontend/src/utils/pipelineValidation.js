import { algorithms } from '../data/algorithms.js';

export function pipelineIssues(steps, wavenumber, language = 'en') {
  const zh = language === 'zh';
  const issues = {};
  let wave = wavenumber || [];
  for (const step of steps) {
    const p = step.params;
    let message = '';
    if (step.type === 'cut') {
      if (p.start === '' || p.end === '' || !Number.isFinite(p.start) || !Number.isFinite(p.end) || p.start >= p.end) {
        message = zh ? '裁剪起点必须小于终点。' : 'Cut start must be smaller than the end.';
      } else if (wave.length) {
        wave = wave.filter(value => value >= p.start && value <= p.end);
        if (!wave.length) message = zh ? '裁剪范围内没有光谱点。' : 'No spectral points in this cut range.';
      }
    } else {
      const algorithm = algorithms.find(item => item.id === step.method);
      for (const field of algorithm?.fields || []) {
        const value = p[field.key];
        if (field.options ? !field.options.includes(value) : value === '' || !Number.isFinite(value) || value < field.min || value > field.max || (field.step !== 'any' && !Number.isInteger(value))) {
          message = zh ? `${field.zh}超出允许范围或格式不正确。` : `${field.label} is outside its allowed range or has an invalid format.`;
          break;
        }
      }
      const length = wave.length;
      if (!message && length && step.method === 'airnet' && length < 4) message = zh ? 'AirNet 至少需要 4 个光谱点。' : 'AirNet requires at least 4 spectral points.';
      if (!message && length && step.method === 'f2p' && length < 4) message = zh ? 'F2P 至少需要 4 个光谱点。' : 'F2P requires at least 4 spectral points.';
      if (!message && step.method === 'sg' && (p.window_size % 2 !== 1 || p.order >= p.window_size || (length && p.window_size > length))) message = zh ? 'SG 窗口必须为奇数、大于多项式阶数，且不超过当前光谱点数。' : 'SG window must be odd, greater than the polynomial order, and no longer than the current spectrum.';
      if (!message && length && step.method === 'wtd') {
        const maximum = Math.max(0, Math.floor(Math.log2(length / (2 * Number(p.wavelet.slice(2)) - 1))));
        if (p.level > maximum) message = zh ? `当前光谱与小波最多支持 ${maximum} 层分解。` : `This spectrum and wavelet support at most ${maximum} decomposition levels.`;
      }
      if (!message && length && step.method === 'aabs' && length < Math.max(100, p.Ln, p.Lb)) message = zh ? 'AABS 要求光谱点数不少于 max(100, Ln, Lb)。' : 'AABS requires at least max(100, Ln, Lb) spectral points.';
      if (!message && length && step.method === 'snip' && p.max_half_window > Math.floor((length - 1) / 2)) message = zh ? 'SNIP 最大半窗口不能超过当前光谱长度的一半。' : 'SNIP maximum half window must not exceed half the current spectral length.';
      if (!message && length && step.method === 'peer' && length < 7) message = zh ? 'PEER 至少需要 7 个光谱点。' : 'PEER requires at least 7 spectral points.';
    }
    if (message) issues[step.id] = message;
  }
  return issues;
}
