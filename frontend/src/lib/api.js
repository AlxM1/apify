const BASE = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || JSON.stringify(err));
  }
  return res.json();
}

export const api = {
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
