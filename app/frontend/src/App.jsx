import React, { useState, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Sidebar from './components/Sidebar';
import SplitView from './components/SplitView';
import Main from './pages/Main';
import Sub from './pages/Sub';
import Review from './pages/Review';

const queryClient = new QueryClient();

const App = () => {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [selectedRoomId, setSelectedRoomId] = useState(null);
  const [currentView, setCurrentView] = useState('main'); // 'main', 'split', 'review'
  const [splitData, setSplitData] = useState({ subRoomId: null, reviewId: null });

  // 키보드 단축키 처리
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'b') {
        e.preventDefault();
        setSidebarOpen(!sidebarOpen);
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        // 룸 검색 기능 (구현 예정)
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [sidebarOpen]);

  const handleRoomSelect = (roomId) => {
    setSelectedRoomId(roomId);
    setCurrentView('main');
    setSplitData({ subRoomId: null, reviewId: null });
  };

  const handleToggleReview = (room) => {
    // room: 검토룸 객체 (parent_room 정보 포함)
    const reviewId = room.room_id;
    
    // 검토룸의 부모(세부룸) 정보를 사용
    const subRoomId = room.sub_room_id || room.parent_room?.room_id;
    
    if (window.innerWidth >= 1024) {
      // 데스크탑: 분할 모드 + 사이드바 자동 닫기
      setSplitData({ subRoomId, reviewId });
      setCurrentView('split');
      setSidebarOpen(false);
    } else {
      // 모바일: 검토룸 단독 뷰
      setSplitData({ subRoomId: null, reviewId });
      setCurrentView('review');
      setSidebarOpen(false);
    }
  };

  const handleBackToMain = () => {
    setCurrentView('main');
    setSplitData({ subRoomId: null, reviewId: null });
  };

  const handleBackToSub = () => {
    if (window.innerWidth >= 1024) {
      setCurrentView('split');
    } else {
      setCurrentView('main');
      setSplitData({ subRoomId: null, reviewId: null });
    }
  };

  const renderContent = () => {
    switch (currentView) {
      case 'split':
        return (
          <SplitView
            leftPanel={<Main roomId={splitData.subRoomId} onToggleReview={handleToggleReview} />} // Sub 대신 Main으로 변경
            rightPanel={<Review reviewId={splitData.reviewId} onBackToSub={handleBackToSub} />}
            defaultRatio={0.4}
            minLeftWidth={360}
            minRightWidth={360}
          />
        );
      case 'review':
        return <Review reviewId={splitData.reviewId} onBackToSub={handleBackToMain} />;
      default:
        return <Main roomId={selectedRoomId} onToggleReview={handleToggleReview} />;
    }
  };

  return (
    <QueryClientProvider client={queryClient}>
      <div className="h-screen bg-bg text-text font-sans">
        <div className="grid h-full" style={{ gridTemplateColumns: sidebarOpen ? '280px 1fr' : '0 1fr' }}>
          {/* 사이드바 */}
          <Sidebar
            isOpen={sidebarOpen}
            onToggle={() => setSidebarOpen(!sidebarOpen)}
            selectedRoomId={selectedRoomId}
            onRoomSelect={handleRoomSelect}
            onToggleReview={handleToggleReview}
            onClose={() => setSidebarOpen(false)}
          />

          {/* 메인 콘텐츠 */}
          <div className="flex flex-col h-full">
            {renderContent()}
          </div>
        </div>
      </div>
    </QueryClientProvider>
  );
};

export default App;
