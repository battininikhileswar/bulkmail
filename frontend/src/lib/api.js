/**
 * Normalizes the backend API base URL from VITE_API_URL or a passed custom URL.
 * Ensures the returned URL always includes the '/api' prefix without duplicate slashes.
 *
 * Supported formats for VITE_API_URL:
 * - 'https://bulkmail-backend-nine.vercel.app'     -> 'https://bulkmail-backend-nine.vercel.app/api'
 * - 'https://bulkmail-backend-nine.vercel.app/'    -> 'https://bulkmail-backend-nine.vercel.app/api'
 * - 'https://bulkmail-backend-nine.vercel.app/api' -> 'https://bulkmail-backend-nine.vercel.app/api'
 * - 'http://localhost:8000'                       -> 'http://localhost:8000/api'
 * - undefined / default                           -> 'http://localhost:8000/api'
 */
export function getApiBaseUrl(customUrl) {
  const envUrl = typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env.VITE_API_URL : undefined;
  const raw = (customUrl || envUrl || 'http://localhost:8000/api')
    .toString()
    .trim()
    .replace(/\/+$/, '');
  if (!raw) return 'http://localhost:8000/api';
  return raw.endsWith('/api') ? raw : `${raw}/api`;
}

export const API_BASE_URL = getApiBaseUrl();
