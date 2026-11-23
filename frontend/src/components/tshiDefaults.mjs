import {legacyDefaults} from './legacyAlgorithms.js';
export function denoiseDefaults(method, context = {}) {
  if (legacyDefaults(method)) return legacyDefaults(method);
  if (method === 'tshi') {
    const wave = context.wavenumber || [];
    const side = Math.min(...(context.shape?.slice(0, 2) || [5, 5]));
    return { center_wavenumber: context.selectedWN ?? wave[Math.floor(wave.length / 2)] ?? 1286,
      half_width: 20, windowsize: side >= 5 ? 5 : 3, count: 100,
      thr1: 1e-5, thr2: 0.3, smoothness: 'legacy', bm3d_enabled: false, bm3d_sigma: 5 };
  }
  if (method === 'sg') return { window_size: 7, order: 3 };
  if (method === 'wtd') return { wavelet: 'db3', level: 3 };
  if (method === 'peer') return { loops: 3, half_k_threshold: 2 };
  return {};
}
