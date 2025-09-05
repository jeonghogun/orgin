import React, { useEffect } from 'react';
import { Routes, Route, useParams } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import SplitView from './components/SplitView';
import Main from './pages/Main';
import Review from './pages/Review';
import { AppProvider, useAppContext } from './context/AppContext';
import EmptyState from './components/common/EmptyState';

// Wrapper component to pass route params to Main page
const MainWrapper = () => {
  const { roomId } = useParams();
  const { setSelectedRoomId } = useAppContext();
  useEffect(() => {
    setSelectedRoomId(roomId || null);
  }, [roomId, setSelectedRoomId]);
  return <Main roomId={roomId} />;
};

// Wrapper component for the Review page
const ReviewWrapper = () => {
  const { reviewId } = useParams();
  return <Review reviewId={reviewId} />;
};

// Wrapper for the Split View
const SplitViewWrapper = () => {
  const { roomId, reviewId } = useParams();
  // In split view, we don't want the sidebar, so we can control it here if needed
  const { setSidebarOpen } = useAppContext();
  useEffect(() => {
    if (window.innerWidth >= 1024) {
      setSidebarOpen(false);
    }
  }, [setSidebarOpen]);

  return (
    <SplitView
      leftPanel={<Main roomId={roomId} isSplitView={true} />}
      rightPanel={<Review reviewId={reviewId} isSplitView={true} />}
      defaultRatio={0.4}
      minLeftWidth={360}
      minRightWidth={360}
    />
  );
};


const AppContent = () => {
  const { sidebarOpen, setSidebarOpen, error } = useAppContext();

  // Keyboard shortcut for sidebar
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'b') {
        e.preventDefault();
        setSidebarOpen(!sidebarOpen);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [sidebarOpen, setSidebarOpen]);

  return (
    <div className="h-screen bg-bg text-text font-sans overflow-hidden">
      {error && (
        <div className="absolute top-5 right-5 bg-danger text-white px-6 py-3 rounded-lg shadow-lg z-50 animate-fade-in">
          <p className="font-semibold">에러 발생</p>
          <p className="text-sm">{error}</p>
        </div>
      )}
      <div className="flex h-full">
        <div className={`flex-shrink-0 ${sidebarOpen ? 'w-[280px]' : 'w-0'} transition-all duration-150`}>
          <Sidebar />
        </div>
        
        <div className="flex-1 overflow-hidden">
          <Routes>
            <Route path="/" element={<MainWrapper />} />
            <Route path="/rooms/:roomId" element={<MainWrapper />} />
            <Route path="/reviews/:reviewId" element={<ReviewWrapper />} />
            <Route path="/rooms/:roomId/reviews/:reviewId" element={<SplitViewWrapper />} />
            <Route path="*" element={<EmptyState message="Page Not Found" />} />
          </Routes>
        </div>
      </div>
    </div>
  );
};

import ErrorBoundary from './components/common/ErrorBoundary';

const App = () => {
  return (
    <ErrorBoundary>
      <AppProvider>
        <AppContent />
      </AppProvider>
    </ErrorBoundary>
  );
};

export default App;
