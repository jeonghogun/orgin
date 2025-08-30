import React, { useState } from 'react';
import { BrowserRouter as Router, Route, Routes, Link } from 'react-router-dom';
import RoomList from './components/RoomList';
import ChatWindow from './components/ChatWindow';
import ReviewPanel from './components/ReviewPanel';
import MetricsDashboard from './components/MetricsDashboard';
import AdminPage from './components/admin/AdminPage';
import './App.css';

function App() {
  const [selectedRoomId, setSelectedRoomId] = useState(null);

  // In a real app, this would come from a user context
  const user = { role: 'admin' };

  return (
    <Router>
      <div className="app-container">
        <header>
          <h1>Origin</h1>
          <nav>
            <Link to="/">Chat</Link>
            <Link to="/metrics">Metrics</Link>
            {user.role === 'admin' && <Link to="/admin">Admin</Link>}
          </nav>
        </header>
        <div className="main-layout">
          <aside className="sidebar">
            <RoomList onRoomSelect={setSelectedRoomId} />
          </aside>
          <main className="content">
            <Routes>
              <Route path="/" element={<ChatWindow roomId={selectedRoomId} />} />
              <Route path="/review/:reviewId" element={<ReviewPanel />} />
              <Route path="/metrics" element={<MetricsDashboard />} />
              {user.role === 'admin' && <Route path="/admin" element={<AdminPage />} />}
            </Routes>
          </main>
        </div>
      </div>
    </Router>
  );
}

export default App;
