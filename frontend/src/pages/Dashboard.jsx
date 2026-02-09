import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.getDashboard(), api.listScrapes({ limit: 10 })])
      .then(([s, j]) => {
        setStats(s);
        setJobs(j);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="loading">Loading...</div>;

  return (
    <div>
      <div className="page-header">
        <h1>Dashboard</h1>
        <p>Overview of your scraping operations</p>
      </div>

      {stats && (
        <div className="stat-grid">
          <div className="stat-card">
            <div className="label">Total Jobs</div>
            <div className="value">{stats.total_jobs}</div>
          </div>
          <div className="stat-card">
            <div className="label">Completed</div>
            <div className="value green">{stats.completed_jobs}</div>
          </div>
          <div className="stat-card">
            <div className="label">Running</div>
            <div className="value blue">{stats.running_jobs}</div>
          </div>
          <div className="stat-card">
            <div className="label">Failed</div>
            <div className="value red">{stats.failed_jobs}</div>
          </div>
          <div className="stat-card">
            <div className="label">Total Results</div>
            <div className="value">{stats.total_results}</div>
          </div>
          <div className="stat-card">
            <div className="label">Results Today</div>
            <div className="value blue">{stats.results_today}</div>
          </div>
          <div className="stat-card">
            <div className="label">Platforms Used</div>
            <div className="value">{stats.platforms_used}</div>
          </div>
          <div className="stat-card">
            <div className="label">Avg Duration</div>
            <div className="value">{stats.avg_duration ? `${stats.avg_duration}s` : '—'}</div>
          </div>
        </div>
      )}

      <div className="flex-between mb-1">
        <h2>Recent Jobs</h2>
        <Link to="/jobs" className="btn-ghost" style={{ padding: '0.4rem 0.75rem', fontSize: '0.8rem' }}>
          View All
        </Link>
      </div>
      <div className="card">
        {jobs.length === 0 ? (
          <div className="empty">No jobs yet. <Link to="/scrape">Start your first scrape</Link></div>
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
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id}>
                    <td><Link to={`/jobs/${job.id}`}>#{job.id}</Link></td>
                    <td>{job.platform}</td>
                    <td>{job.action}</td>
                    <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{job.target}</td>
                    <td><span className={`badge badge-${job.status}`}>{job.status}</span></td>
                    <td>{job.result_count}</td>
                    <td>{new Date(job.created_at).toLocaleString()}</td>
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
