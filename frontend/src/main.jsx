import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// Intercept fetch calls to ensure credentials: 'include' and 401 handling
const originalFetch = window.fetch;
window.fetch = async function (input, init = {}) {
  const url = typeof input === 'string' ? input : input?.url;
  if (url && (url.includes('/api') || url.includes(':8000') || (import.meta.env.VITE_API_URL && url.includes(import.meta.env.VITE_API_URL)))) {
    init = { ...init, credentials: 'include' };
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
