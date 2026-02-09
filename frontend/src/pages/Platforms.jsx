import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play } from 'lucide-react';
import { api } from '../lib/api';

const PLATFORM_ICONS = {
  youtube: '#FF0000',
  reddit: '#FF4500',
  bluesky: '#0085FF',
  hackernews: '#FF6600',
  medium: '#000000',
  tumblr: '#36465D',
  twitter: '#1DA1F2',
  instagram: '#E4405F',
  tiktok: '#010101',
  pinterest: '#E60023',
  threads: '#000000',
  mastodon: '#6364FF',
  telegram: '#26A5E4',
  twitch: '#9146FF',
  discord: '#5865F2',
  quora: '#B92B27',
  snapchat: '#FFFC00',
  kick: '#53FC18',
  substack: '#FF6719',
  rumble: '#85C742',
};

export default function Platforms() {
  const [platforms, setPlatforms] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    api.getPlatforms().then(setPlatforms).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="loading">Loading...</div>;

  return (
    <div>
      <div className="page-header">
        <h1>Platforms</h1>
        <p>{platforms.length} scrapers available</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem' }}>
        {platforms.map((p) => (
          <div key={p.name} className="card" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div
              style={{
                width: 40,
                height: 40,
                borderRadius: 8,
                background: PLATFORM_ICONS[p.name] || '#6366f1',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '1rem',
                fontWeight: 700,
                color: p.name === 'snapchat' ? '#000' : '#fff',
                flexShrink: 0,
              }}
            >
              {p.name.slice(0, 2).toUpperCase()}
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, textTransform: 'capitalize' }}>{p.name}</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Rate limit: {p.rate_limit} req/s
              </div>
            </div>
            <button
              className="btn-primary"
              style={{ padding: '0.4rem 0.75rem', fontSize: '0.8rem' }}
              onClick={() => navigate(`/scrape?platform=${p.name}`)}
              title={`Scrape ${p.name}`}
            >
              <Play size={14} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
