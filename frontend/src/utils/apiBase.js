// Keep RamanCloud requests separate from other applications on the same host.
export const API_BASE = (import.meta.env.VITE_API_BASE || '/ramancloud-api').replace(/\/$/, '');
