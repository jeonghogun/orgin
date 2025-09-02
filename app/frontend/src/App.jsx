import React, { useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Sidebar from './components/Sidebar';
import SplitView from './components/SplitView';
import Main from './pages/Main';
import Sub from './pages/Sub';
import Review from './pages/Review';
import { AppProvider, useAppContext } from './context/AppContext';

const queryClient = new QueryClient();

const AppContent = () => {
  const {
    sidebarOpen,
    setSidebarOpen,
    currentView,
    splitData,
    VIEWS,
    handleToggleReview,
    handleBackToSub,
    handleBackToMain,
    selectedRoomId,
    error,
  } = useAppContext();

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

  const renderContent = () => {
    switch (currentView) {
      case VIEWS.SPLIT:
        return (
          <SplitView
            leftPanel={<Sub roomId={splitData.subRoomId} onToggleReview={handleToggleReview} />}
            rightPanel={<Review reviewId={splitData.reviewId} />}
            defaultRatio={0.4} // 좌측 2/5, 우측 3/5
            minLeftWidth={360}
            minRightWidth={360}
          />
        );
      case VIEWS.REVIEW:
        return <Review reviewId={splitData.reviewId} />;
      default:
        return <Main roomId={selectedRoomId} />;
    }
  };

  return (
    <div className="h-screen bg-bg text-text font-sans">
      {error && (
        <div className="absolute top-5 right-5 bg-danger text-white px-6 py-3 rounded-lg shadow-lg z-50 animate-fade-in">
          <p className="font-semibold">에러 발생</p>
          <p className="text-sm">{error}</p>
        </div>
      )}
      <div className="grid h-full" style={{ gridTemplateColumns: sidebarOpen ? '280px 1fr' : '0 1fr' }}>
        <Sidebar />
        <div className="flex flex-col h-full">
          {renderContent()}
        </div>
      </div>
    </div>
  );
};

const App = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <AppProvider>
        <AppContent />
      </AppProvider>
    </QueryClientProvider>
  );
};

export default App;
