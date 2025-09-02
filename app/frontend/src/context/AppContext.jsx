import React, { createContext, useState, useContext } from 'react';
import { ROOM_TYPES } from '../constants';

const AppContext = createContext();

const VIEWS = {
  MAIN: 'main',
  SPLIT: 'split',
  REVIEW: 'review',
};

export const AppProvider = ({ children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [selectedRoomId, setSelectedRoomId] = useState(null);
  const [currentView, setCurrentView] = useState(VIEWS.MAIN);
  const [splitData, setSplitData] = useState({ subRoomId: null, reviewId: null });
  const [error, setError] = useState(null);

  const showError = (message, duration = 5000) => {
    setError(message);
    setTimeout(() => {
      setError(null);
    }, duration);
  };

  const handleRoomSelect = (roomId) => {
    setSelectedRoomId(roomId);
    setCurrentView(VIEWS.MAIN);
    setSplitData({ subRoomId: null, reviewId: null });
    // 룸 선택 시 사이드바 열기 (모바일에서 유용)
    if (window.innerWidth < 1024) {
      setSidebarOpen(true);
    }
  };

  const handleToggleReview = (room) => {
    const reviewId = room.room_id;
    const subRoomId = room.sub_room_id || room.parent_room?.room_id;

    // 먼저 사이드바를 강제로 닫기
    setSidebarOpen(false);

    if (window.innerWidth >= 1024) {
      // 데스크탑: 분할 모드 + 사이드바 자동 닫기
      setSplitData({ subRoomId, reviewId });
      setCurrentView(VIEWS.SPLIT);
    } else {
      // 모바일: 검토룸 단독 뷰 + 사이드바 자동 닫기
      setSplitData({ subRoomId: null, reviewId });
      setCurrentView(VIEWS.REVIEW);
    }
  };

  const handleBackToMain = () => {
    setCurrentView(VIEWS.MAIN);
    setSplitData({ subRoomId: null, reviewId: null });
    setSidebarOpen(true); // 메인으로 돌아가면 사이드바 다시 열기
  };

  const handleBackToSub = () => {
    if (window.innerWidth >= 1024) {
      setCurrentView(VIEWS.SPLIT);
      setSidebarOpen(false); // 분할 모드에서는 사이드바 닫힌 상태 유지
    } else {
      setCurrentView(VIEWS.MAIN);
      setSplitData({ subRoomId: null, reviewId: null });
      setSidebarOpen(true); // 메인으로 돌아가면 사이드바 다시 열기
    }
  };

  const value = {
    sidebarOpen,
    setSidebarOpen,
    selectedRoomId,
    handleRoomSelect,
    currentView,
    splitData,
    handleToggleReview,
    handleBackToMain,
    handleBackToSub,
    VIEWS,
    error,
    showError,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
};

export const useAppContext = () => {
  const context = useContext(AppContext);
  if (context === undefined) {
    throw new Error('useAppContext must be used within an AppProvider');
  }
  return context;
};
