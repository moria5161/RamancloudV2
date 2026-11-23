export const FEEDBACK_CATEGORIES = [
  ['bug', ['问题或报错', 'Problem or error']],
  ['suggestion', ['功能建议', 'Feature suggestion']],
  ['data', ['数据格式兼容', 'Data compatibility']],
  ['tutorial', ['教程与说明', 'Tutorial or documentation']],
  ['other', ['其他', 'Other']],
];
export const FEEDBACK_STATUSES = [
  ['new', ['待处理', 'Pending']],
  ['in_progress', ['处理中', 'In progress']],
  ['resolved', ['已处理', 'Resolved']],
];

export const FEEDBACK_PAGE_KEYS = {
  '/': 'homepage', '/tutorial': 'tutorial', '/ai-analysis': 'aiAnalysis',
  '/hyperspectral': 'hyperspectralProcessing', '/spectral-unmixing': 'spectralUnmixing',
  '/library-matching': 'libraryMatching', '/structure-generation': 'structureGeneration',
  '/projects': 'projectDataManagement', '/analysis-history': 'analysisHistory',
  '/extra-tools': 'extraTools', '/account': 'personalSpace', '/contributors': 'contributors',
  '/feedback': 'feedback',
};

// crypto.randomUUID is unavailable on some HTTP deployments; getRandomValues
// remains available there. This key makes retries idempotent, not an auth token.
export function feedbackRequestId() {
  if (globalThis.crypto.randomUUID) return globalThis.crypto.randomUUID();
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
