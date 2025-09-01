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

  const handleRoomSelect = (roomId) => {
    setSelectedRoomId(roomId);
    setCurrentView(VIEWS.MAIN);
    setSplitData({ subRoomId: null, reviewId: null });
  };

  const handleToggleReview = (room) => {
    const reviewId = room.room_id;
    const subRoomId = room.sub_room_id || room.parent_room?.room_id;

    if (window.innerWidth >= 1024) {
      setSplitData({ subRoomId, reviewId });
      setCurrentView(VIEWS.SPLIT);
      setSidebarOpen(false);
    } else {
      setSplitData({ subRoomId: null, reviewId });
      setCurrentView(VIEWS.REVIEW);
      setSidebarOpen(false);
    }
  };

  const handleBackToMain = () => {
    setCurrentView(VIEWS.MAIN);
    setSplitData({ subRoomId: null, reviewId: null });
  };

  const handleBackToSub = () => {
    if (window.innerWidth >= 1024) {
      setCurrentView(VIEWS.SPLIT);
    } else {
      setCurrentView(VIEWS.MAIN);
      setSplitData({ subRoomId: null, reviewId: null });
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
