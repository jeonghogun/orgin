import React, { useState } from 'react';
import { BrowserRouter as Router, Route, Routes, Link } from 'react-router-dom';
import RoomList from './components/RoomList';
import ChatWindow from './components/ChatWindow';
import ReviewPanel from './components/ReviewPanel';
import MetricsDashboard from './components/MetricsDashboard';
import './App.css';

function App() {
  const [selectedRoomId, setSelectedRoomId] = useState(null);

  return (
    <Router>
      <div className="app-container">
        <header>
          <h1>Origin</h1>
          <nav>
            <Link to="/">Chat</Link>
            <Link to="/metrics">Metrics</Link>
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
            </Routes>
          </main>
        </div>
      </div>
    </Router>
  );
}

export default App;
