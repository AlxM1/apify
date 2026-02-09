import { useEffect, useState } from 'react';
import { Download, Search } from 'lucide-react';
import { api } from '../lib/api';

export default function Results() {
  const [results, setResults] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ platform: '', content_type: '', q: '' });
  const [searchInput, setSearchInput] = useState('');

  const load = () => {
    setLoading(true);
    const params = { limit: 100 };
    if (filters.platform) params.platform = filters.platform;
    if (filters.content_type) params.content_type = filters.content_type;
    if (filters.q) params.q = filters.q;
    Promise.all([api.searchResults(params), api.getResultStats()])
      .then(([r, s]) => { setResults(r); setStats(s); })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [filters.platform, filters.content_type, filters.q]);

  const doSearch = (e) => {
    e.preventDefault();
    setFilters((f) => ({ ...f, q: searchInput }));
  };

  return (
    <div>
      <div className="flex-between page-header">
        <div>
          <h1>Results</h1>
          <p>{stats ? `${stats.total_results} total results` : 'Browse all scraped data'}</p>
        </div>
        <div className="flex-gap">
          <a
            href={api.exportResults({ ...filters, format: 'json' })}
            className="btn-ghost flex-gap"
            style={{ padding: '0.5rem 0.75rem', textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}
            download
          >
            <Download size={14} /> JSON
          </a>
          <a
            href={api.exportResults({ ...filters, format: 'csv' })}
            className="btn-ghost flex-gap"
            style={{ padding: '0.5rem 0.75rem', textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}
            download
          >
            <Download size={14} /> CSV
          </a>
        </div>
      </div>

      {/* Filters */}
      <div className="flex-gap mb-1" style={{ flexWrap: 'wrap' }}>
        <select
          value={filters.platform}
          onChange={(e) => setFilters((f) => ({ ...f, platform: e.target.value }))}
          style={{ width: 160 }}
        >
          <option value="">All Platforms</option>
          {stats && Object.keys(stats.by_platform || {}).sort().map((p) => (
            <option key={p} value={p}>{p} ({stats.by_platform[p]})</option>
          ))}
        </select>
        <select
          value={filters.content_type}
          onChange={(e) => setFilters((f) => ({ ...f, content_type: e.target.value }))}
          style={{ width: 160 }}
        >
          <option value="">All Types</option>
          {stats && Object.keys(stats.by_content_type || {}).sort().map((t) => (
            <option key={t} value={t}>{t} ({stats.by_content_type[t]})</option>
          ))}
        </select>
        <form onSubmit={doSearch} className="flex-gap" style={{ flex: 1, minWidth: 200 }}>
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search in data..."
            style={{ flex: 1 }}
          />
          <button type="submit" className="btn-primary flex-gap">
            <Search size={14} /> Search
          </button>
        </form>
      </div>

      <div className="card">
        {loading ? (
          <div className="loading">Loading...</div>
        ) : results.length === 0 ? (
          <div className="empty">No results found</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Platform</th>
                  <th>Type</th>
                  <th>Data</th>
                  <th>URL</th>
                  <th>Scraped</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r) => (
                  <tr key={r.id}>
                    <td>{r.platform}</td>
                    <td><span className="badge badge-completed">{r.content_type}</span></td>
                    <td style={{ maxWidth: 400 }}>
                      <details>
                        <summary style={{ cursor: 'pointer', color: 'var(--text-dim)' }}>
                          {dataPreview(r.data)}
                        </summary>
                        <pre className="json-view" style={{ marginTop: '0.5rem' }}>
                          {JSON.stringify(r.data, null, 2)}
                        </pre>
                      </details>
                    </td>
                    <td>
                      {r.url && (
                        <a href={r.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: '0.8rem' }}>
                          {r.url.length > 40 ? r.url.slice(0, 40) + '...' : r.url}
                        </a>
                      )}
                    </td>
                    <td style={{ whiteSpace: 'nowrap', fontSize: '0.8rem' }}>
                      {r.scraped_at ? new Date(r.scraped_at).toLocaleString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function dataPreview(data) {
  const fields = ['title', 'name', 'username', 'text', 'display_name', 'slug', 'caption', 'bio'];
  for (const f of fields) {
    if (data[f]) {
      const val = String(data[f]);
      return val.length > 80 ? val.slice(0, 80) + '...' : val;
    }
  }
  const keys = Object.keys(data);
  return keys.length > 0 ? `{${keys.slice(0, 4).join(', ')}${keys.length > 4 ? ', ...' : ''}}` : '{}';
}
