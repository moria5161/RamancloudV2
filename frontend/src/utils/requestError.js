export async function requestErrorDetail(error) {
  let data = error?.response?.data;
  if (data instanceof Blob) {
    try { data = JSON.parse(await data.text()); } catch { return ''; }
  }
  const detail = data?.detail || data?.msg;
  return typeof detail === 'string' ? detail : '';
}
