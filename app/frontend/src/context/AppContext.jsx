import React, { createContext, useState, useContext } from 'react';

const AppContext = createContext();

export const AppProvider = ({ children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [selectedRoomId, setSelectedRoomId] = useState(null);
  const [error, setError] = useState(null);

  const showError = (message, duration = 5000) => {
    setError(message);
    setTimeout(() => {
      setError(null);
    }, duration);
  };

  // This function is kept to set the "active" state in the sidebar
  const handleRoomSelect = (roomId) => {
    setSelectedRoomId(roomId);
    if (window.innerWidth < 1024) {
      setSidebarOpen(true);
    }
  };

  const value = {
    sidebarOpen,
    setSidebarOpen,
    selectedRoomId,
    setSelectedRoomId, // Expose setter for direct use
    handleRoomSelect, // Keep for now for sidebar active state
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
