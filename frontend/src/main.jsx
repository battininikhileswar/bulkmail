import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { API_BASE_URL } from '@/lib/api'

// Intercept fetch calls to ensure credentials: 'include', Authorization header, and 401 handling
const originalFetch = window.fetch;
window.fetch = async function (input, init = {}) {
  const url = typeof input === 'string' ? input : input?.url;
  const isApiCall = url && (url.includes('/api') || url.includes(':8000') || (API_BASE_URL && url.includes(API_BASE_URL)));

  if (isApiCall) {
    const headers = new Headers(init.headers || {});
    const storedToken = localStorage.getItem('bulkmail_session');
    if (storedToken && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${storedToken}`);
    }
    init = {
      ...init,
      headers,
      credentials: 'include',
    };
  }

  const response = await originalFetch(input, init);
  if (response.status === 401 && url && !url.includes('/auth/me') && !url.includes('/auth/login')) {
    window.dispatchEvent(new CustomEvent('auth:unauthorized'));
  }
  return response;
};

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
