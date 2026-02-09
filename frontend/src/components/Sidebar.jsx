import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Play,
  List,
  Database,
  Globe,
  Clock,
} from 'lucide-react';

const links = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/scrape', icon: Play, label: 'New Scrape' },
  { to: '/jobs', icon: List, label: 'Jobs' },
  { to: '/schedules', icon: Clock, label: 'Schedules' },
  { to: '/results', icon: Database, label: 'Results' },
  { to: '/platforms', icon: Globe, label: 'Platforms' },
];

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <Globe size={22} />
        Apify Suite
      </div>
      <nav className="sidebar-nav">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `sidebar-link${isActive ? ' active' : ''}`
            }
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
