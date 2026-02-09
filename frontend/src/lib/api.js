const BASE = '/api';

// API key stored in localStorage (if auth is enabled)
function authHeaders() {
  const key = localStorage.getItem('apiKey');
  if (key) return { 'X-API-Key': key };
  return {};
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || JSON.stringify(err));
  }
  return res.json();
}

export const api = {
  // Auth
  getAuthStatus: () => request('/auth/status'),
  setApiKey: (key) => localStorage.setItem('apiKey', key),
  clearApiKey: () => localStorage.removeItem('apiKey'),

  // Dashboard
  getDashboard: () => request('/dashboard'),

  // Platforms
  getPlatforms: () => request('/platforms'),

  // Scrape jobs
  createScrape: (data) =>
    request('/scrapes', { method: 'POST', body: JSON.stringify(data) }),
  listScrapes: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/scrapes${qs ? `?${qs}` : ''}`);
  },
  getScrape: (id) => request(`/scrapes/${id}`),
  deleteScrape: (id) => request(`/scrapes/${id}`, { method: 'DELETE' }),
  cancelScrape: (id) => request(`/scrapes/${id}/cancel`, { method: 'POST' }),
  retryScrape: (id) => request(`/scrapes/${id}/retry`, { method: 'POST' }),
  getScrapeResults: (id, params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/scrapes/${id}/results${qs ? `?${qs}` : ''}`);
  },

  // Schedules
  listSchedules: () => request('/schedules'),
  createSchedule: (data) =>
    request('/schedules', { method: 'POST', body: JSON.stringify(data) }),
  updateSchedule: (id, data) =>
    request(`/schedules/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteSchedule: (id) => request(`/schedules/${id}`, { method: 'DELETE' }),

  // Bulk
  bulkScrape: (data) =>
    request('/bulk/scrape', { method: 'POST', body: JSON.stringify(data) }),
  deduplicate: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/bulk/deduplicate${qs ? `?${qs}` : ''}`, { method: 'POST' });
  },

  // Results
  searchResults: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/results${qs ? `?${qs}` : ''}`);
  },
  getResultStats: () => request('/results/stats'),
  exportResults: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return `${BASE}/results/export${qs ? `?${qs}` : ''}`;
  },
};

// WebSocket for real-time updates
export function connectWS(onMessage) {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${proto}//${location.host}/ws`);
  ws.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data));
    } catch {}
  };
  ws.onclose = () => {
    // Reconnect after 3 seconds
    setTimeout(() => connectWS(onMessage), 3000);
  };
  return ws;
}
