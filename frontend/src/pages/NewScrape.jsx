import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Play } from 'lucide-react';
import { api } from '../lib/api';

export default function NewScrape() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [platforms, setPlatforms] = useState([]);
  const [form, setForm] = useState({
    platform: '',
    action: 'posts',
    target: '',
    max_results: 100,
    proxy: '',
    delay: 1.0,
    headless: true,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api.getPlatforms().then(setPlatforms).catch(() => {});
    const p = searchParams.get('platform');
    if (p) setForm((f) => ({ ...f, platform: p }));
  }, []);

  const set = (key) => (e) => {
    const val = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setForm((f) => ({ ...f, [key]: val }));
  };

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (!form.platform || !form.target) {
      setError('Platform and target are required.');
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        ...form,
        max_results: Number(form.max_results),
        delay: Number(form.delay),
        proxy: form.proxy || null,
      };
      const job = await api.createScrape(payload);
      navigate(`/jobs/${job.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const placeholders = {
    profile: 'Username or profile URL',
    posts: 'Username, subreddit, hashtag, or URL',
    search: 'Search query',
  };

  return (
    <div>
      <div className="page-header">
        <h1>New Scrape</h1>
        <p>Configure and launch a new scraping job</p>
      </div>

      <div className="card" style={{ maxWidth: 640 }}>
        {error && <div className="error-msg">{error}</div>}

        <form onSubmit={submit}>
          <div className="form-grid">
            <div className="form-group">
              <label>Platform</label>
              <select value={form.platform} onChange={set('platform')}>
                <option value="">Select platform...</option>
                {platforms.map((p) => (
                  <option key={p.name} value={p.name}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>Action</label>
              <select value={form.action} onChange={set('action')}>
                <option value="profile">Profile</option>
                <option value="posts">Posts / Content</option>
                <option value="search">Search</option>
              </select>
            </div>

            <div className="form-group full">
              <label>Target</label>
              <input
                type="text"
                value={form.target}
                onChange={set('target')}
                placeholder={placeholders[form.action]}
              />
            </div>

            <div className="form-group">
              <label>Max Results</label>
              <input
                type="number"
                value={form.max_results}
                onChange={set('max_results')}
                min={1}
                max={10000}
              />
            </div>

            <div className="form-group">
              <label>Delay (seconds)</label>
              <input
                type="number"
                value={form.delay}
                onChange={set('delay')}
                min={0}
                step={0.1}
              />
            </div>

            <div className="form-group full">
              <label>Proxy (optional)</label>
              <input
                type="text"
                value={form.proxy}
                onChange={set('proxy')}
                placeholder="http://user:pass@host:port"
              />
            </div>

            <div className="form-group">
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <input
                  type="checkbox"
                  checked={form.headless}
                  onChange={set('headless')}
                  style={{ width: 'auto' }}
                />
                Headless browser
              </label>
            </div>
          </div>

          <div className="form-actions">
            <button type="submit" className="btn-primary flex-gap" disabled={submitting}>
              <Play size={16} />
              {submitting ? 'Launching...' : 'Launch Scrape'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
