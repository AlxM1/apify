import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw, Trash2 } from 'lucide-react';
import { api } from '../lib/api';

export default function Jobs() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({ platform: '', status: '' });

  const load = () => {
    setLoading(true);
    const params = { limit: 100 };
    if (filter.platform) params.platform = filter.platform;
    if (filter.status) params.status = filter.status;
    api.listScrapes(params)
      .then(setJobs)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [filter.platform, filter.status]);

  // Auto-refresh while any job is running
  useEffect(() => {
    const hasRunning = jobs.some((j) => j.status === 'running' || j.status === 'pending');
    if (!hasRunning) return;
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [jobs]);

  const deleteJob = async (id) => {
    if (!confirm(`Delete job #${id}?`)) return;
    await api.deleteScrape(id);
    load();
  };

  return (
    <div>
      <div className="flex-between page-header">
        <div>
          <h1>Jobs</h1>
          <p>All scraping jobs</p>
        </div>
        <button className="btn-ghost flex-gap" onClick={load}>
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>

      <div className="flex-gap mb-1">
        <select
          value={filter.platform}
          onChange={(e) => setFilter((f) => ({ ...f, platform: e.target.value }))}
          style={{ width: 160 }}
        >
          <option value="">All Platforms</option>
          {[...new Set(jobs.map((j) => j.platform))].sort().map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
        <select
          value={filter.status}
          onChange={(e) => setFilter((f) => ({ ...f, status: e.target.value }))}
          style={{ width: 140 }}
        >
          <option value="">All Status</option>
          <option value="completed">Completed</option>
          <option value="running">Running</option>
          <option value="pending">Pending</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </select>
      </div>

      <div className="card">
        {loading ? (
          <div className="loading">Loading...</div>
        ) : jobs.length === 0 ? (
          <div className="empty">No jobs found</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Platform</th>
                  <th>Action</th>
                  <th>Target</th>
                  <th>Status</th>
                  <th>Results</th>
                  <th>Duration</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id}>
                    <td><Link to={`/jobs/${job.id}`}>#{job.id}</Link></td>
                    <td>{job.platform}</td>
                    <td>{job.action}</td>
                    <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {job.target}
                    </td>
                    <td><span className={`badge badge-${job.status}`}>{job.status}</span></td>
                    <td>{job.result_count}</td>
                    <td>{job.duration_seconds ? `${job.duration_seconds.toFixed(1)}s` : '—'}</td>
                    <td>{new Date(job.created_at).toLocaleString()}</td>
                    <td>
                      <button
                        className="btn-ghost"
                        style={{ padding: '0.25rem 0.5rem' }}
                        onClick={() => deleteJob(job.id)}
                        title="Delete"
                      >
                        <Trash2 size={14} />
                      </button>
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
