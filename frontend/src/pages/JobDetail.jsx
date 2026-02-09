import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, RefreshCw, XCircle, RotateCw, Download } from 'lucide-react';
import { api } from '../lib/api';

export default function JobDetail() {
  const { id } = useParams();
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = () => {
    api.getScrape(id)
      .then(setJob)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [id]);

  // Auto-refresh while running
  useEffect(() => {
    if (!job || (job.status !== 'running' && job.status !== 'pending')) return;
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
  }, [job]);

  const cancel = async () => {
    await api.cancelScrape(id);
    load();
  };

  const retry = async () => {
    const newJob = await api.retryScrape(id);
    window.location.href = `/jobs/${newJob.id}`;
  };

  if (loading) return <div className="loading">Loading...</div>;
  if (error) return <div className="error-msg">{error}</div>;
  if (!job) return <div className="empty">Job not found</div>;

  return (
    <div>
      <div className="page-header">
        <Link to="/jobs" className="flex-gap" style={{ fontSize: '0.85rem', marginBottom: '0.5rem', display: 'inline-flex' }}>
          <ArrowLeft size={14} /> Back to Jobs
        </Link>
        <div className="flex-between">
          <div>
            <h1>Job #{job.id}</h1>
            <p>{job.platform} / {job.action} / {job.target}</p>
          </div>
          <div className="flex-gap">
            {(job.status === 'running' || job.status === 'pending') && (
              <button className="btn-danger flex-gap" onClick={cancel}>
                <XCircle size={14} /> Cancel
              </button>
            )}
            {job.status === 'failed' && (
              <button className="btn-primary flex-gap" onClick={retry}>
                <RotateCw size={14} /> Retry
              </button>
            )}
            {job.result_count > 0 && (
              <a
                href={api.exportResults({ job_id: job.id, format: 'json' })}
                className="btn-ghost flex-gap"
                style={{ padding: '0.5rem 0.75rem', textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}
                download
              >
                <Download size={14} /> Export
              </a>
            )}
            <button className="btn-ghost flex-gap" onClick={load}>
              <RefreshCw size={14} /> Refresh
            </button>
          </div>
        </div>
      </div>

      {/* Job info cards */}
      <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
        <div className="stat-card">
          <div className="label">Status</div>
          <div><span className={`badge badge-${job.status}`}>{job.status}</span></div>
        </div>
        <div className="stat-card">
          <div className="label">Results</div>
          <div className="value">{job.result_count}</div>
        </div>
        <div className="stat-card">
          <div className="label">Duration</div>
          <div className="value">{job.duration_seconds ? `${job.duration_seconds.toFixed(1)}s` : '—'}</div>
        </div>
        <div className="stat-card">
          <div className="label">Max Results</div>
          <div className="value">{job.max_results}</div>
        </div>
      </div>

      {job.error && (
        <div className="error-msg" style={{ whiteSpace: 'pre-wrap', marginBottom: '1rem' }}>
          {job.error}
        </div>
      )}

      {/* Results */}
      {job.results && job.results.length > 0 && (
        <div className="card">
          <h3 style={{ marginBottom: '1rem' }}>Results ({job.results.length})</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Type</th>
                  <th>Data Preview</th>
                  <th>URL</th>
                </tr>
              </thead>
              <tbody>
                {job.results.map((r, i) => {
                  const preview = dataPreview(r.data);
                  return (
                    <tr key={r.id}>
                      <td>{i + 1}</td>
                      <td><span className="badge badge-completed">{r.content_type}</span></td>
                      <td style={{ maxWidth: 400 }}>
                        <details>
                          <summary style={{ cursor: 'pointer', color: 'var(--text-dim)' }}>
                            {preview}
                          </summary>
                          <pre className="json-view" style={{ marginTop: '0.5rem' }}>
                            {JSON.stringify(r.data, null, 2)}
                          </pre>
                        </details>
                      </td>
                      <td>
                        {r.url && (
                          <a href={r.url} target="_blank" rel="noopener noreferrer"
                             style={{ fontSize: '0.8rem', wordBreak: 'break-all', maxWidth: 200, display: 'inline-block' }}>
                            {r.url.length > 50 ? r.url.slice(0, 50) + '...' : r.url}
                          </a>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function dataPreview(data) {
  // Show the most interesting field
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
