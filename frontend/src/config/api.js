export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export function apiUrl(path) {
  return `${API_BASE}${path}`
}

export function mediaUrl(path) {
  if (!path) return ''
  const normalized = path.replace(/\\/g, '/')
  if (normalized.startsWith('http://') || normalized.startsWith('https://')) return normalized
  return `${API_BASE}/${normalized}`
}
