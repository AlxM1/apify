import { useEffect, useState } from 'react';
import { Clock, Plus, Trash2, ToggleLeft, ToggleRight } from 'lucide-react';
import { api } from '../lib/api';

export default function Schedules() {
  const [schedules, setSchedules] = useState([]);
  const [platforms, setPlatforms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: '',
    platform: '',
    action: 'posts',
    target: '',
    max_results: 100,
    cron_expression: '0 */6 * * *',
  });
  const [error, setError] = useState('');

  const load = () => {
    setLoading(true);
    Promise.all([api.listSchedules(), api.getPlatforms()])
      .then(([s, p]) => { setSchedules(s); setPlatforms(p); })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (!form.name || !form.platform || !form.target) {
      setError('Name, platform, and target are required.');
      return;
    }
    try {
      await api.createSchedule({
        ...form,
        max_results: Number(form.max_results),
        config: {},
      });
      setShowForm(false);
      setForm({ name: '', platform: '', action: 'posts', target: '', max_results: 100, cron_expression: '0 */6 * * *' });
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const toggle = async (sj) => {
    await api.updateSchedule(sj.id, { enabled: !sj.enabled });
    load();
  };

  const remove = async (id) => {
    if (!confirm(`Delete schedule #${id}?`)) return;
    await api.deleteSchedule(id);
    load();
  };

  const cronPresets = [
    { label: 'Every hour', value: '0 * * * *' },
    { label: 'Every 6 hours', value: '0 */6 * * *' },
    { label: 'Every 12 hours', value: '0 */12 * * *' },
    { label: 'Daily at midnight', value: '0 0 * * *' },
    { label: 'Weekly (Sunday)', value: '0 0 * * 0' },
  ];

  return (
    <div>
      <div className="flex-between page-header">
        <div>
          <h1>Schedules</h1>
          <p>Recurring scrape jobs on a cron schedule</p>
        </div>
        <button className="btn-primary flex-gap" onClick={() => setShowForm(!showForm)}>
          <Plus size={16} /> New Schedule
        </button>
      </div>

      {showForm && (
        <div className="card mb-1" style={{ maxWidth: 640 }}>
          {error && <div className="error-msg">{error}</div>}
          <form onSubmit={submit}>
            <div className="form-grid">
              <div className="form-group full">
                <label>Name</label>
                <input value={form.name} onChange={set('name')} placeholder="e.g. Daily Reddit r/python" />
              </div>
              <div className="form-group">
                <label>Platform</label>
                <select value={form.platform} onChange={set('platform')}>
                  <option value="">Select...</option>
                  {platforms.map((p) => (
                    <option key={p.name} value={p.name}>{p.name}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Action</label>
                <select value={form.action} onChange={set('action')}>
                  <option value="profile">Profile</option>
                  <option value="posts">Posts</option>
                  <option value="search">Search</option>
                </select>
              </div>
              <div className="form-group full">
                <label>Target</label>
                <input value={form.target} onChange={set('target')} placeholder="Username, subreddit, query..." />
              </div>
              <div className="form-group">
                <label>Max Results</label>
                <input type="number" value={form.max_results} onChange={set('max_results')} min={1} />
              </div>
              <div className="form-group">
                <label>Cron Expression</label>
                <input value={form.cron_expression} onChange={set('cron_expression')} placeholder="0 */6 * * *" />
              </div>
              <div className="form-group full">
                <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  Presets: {cronPresets.map((p) => (
                    <button
                      key={p.value}
                      type="button"
                      className="btn-ghost"
                      style={{ padding: '0.2rem 0.5rem', fontSize: '0.7rem', margin: '0 0.25rem' }}
                      onClick={() => setForm((f) => ({ ...f, cron_expression: p.value }))}
                    >
                      {p.label}
                    </button>
                  ))}
                </label>
              </div>
            </div>
            <div className="form-actions">
              <button type="submit" className="btn-primary">Create Schedule</button>
              <button type="button" className="btn-ghost" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      <div className="card">
        {loading ? (
          <div className="loading">Loading...</div>
        ) : schedules.length === 0 ? (
          <div className="empty">No scheduled jobs yet</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Platform</th>
                  <th>Action</th>
                  <th>Target</th>
                  <th>Cron</th>
                  <th>Last Run</th>
                  <th>Next Run</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {schedules.map((sj) => (
                  <tr key={sj.id}>
                    <td style={{ fontWeight: 600 }}>{sj.name}</td>
                    <td>{sj.platform}</td>
                    <td>{sj.action}</td>
                    <td style={{ maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {sj.target}
                    </td>
                    <td><code style={{ fontSize: '0.75rem' }}>{sj.cron_expression}</code></td>
                    <td style={{ fontSize: '0.8rem' }}>{sj.last_run ? new Date(sj.last_run).toLocaleString() : '—'}</td>
                    <td style={{ fontSize: '0.8rem' }}>{sj.next_run ? new Date(sj.next_run).toLocaleString() : '—'}</td>
                    <td>
                      <button
                        className="btn-ghost"
                        style={{ padding: '0.2rem 0.5rem' }}
                        onClick={() => toggle(sj)}
                        title={sj.enabled ? 'Disable' : 'Enable'}
                      >
                        {sj.enabled
                          ? <ToggleRight size={18} style={{ color: 'var(--green)' }} />
                          : <ToggleLeft size={18} style={{ color: 'var(--text-muted)' }} />}
                      </button>
                    </td>
                    <td>
                      <button
                        className="btn-ghost"
                        style={{ padding: '0.2rem 0.5rem' }}
                        onClick={() => remove(sj.id)}
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
