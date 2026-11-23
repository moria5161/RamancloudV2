export function apiErrorMessage(error, fallback = 'Request failed') {
  const detail = error?.response?.data?.detail ?? error?.response?.data?.msg;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map(item => typeof item === 'string' ? item : typeof item?.msg === 'string' ? item.msg : '').filter(Boolean);
    if (messages.length) return messages.join('; ');
  }
  if (typeof detail?.msg === 'string') return detail.msg;
  return fallback;
}
