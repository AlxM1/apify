import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import NewScrape from './pages/NewScrape';
import Jobs from './pages/Jobs';
import JobDetail from './pages/JobDetail';
import Results from './pages/Results';
import Platforms from './pages/Platforms';

export default function App() {
  return (
    <BrowserRouter>
      <Sidebar />
      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/scrape" element={<NewScrape />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/jobs/:id" element={<JobDetail />} />
          <Route path="/results" element={<Results />} />
          <Route path="/platforms" element={<Platforms />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
