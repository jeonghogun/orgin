import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';

import SearchPanel from './components/conversation/SearchPanel';
import { AppProvider } from './context/AppContext';
import Main from './pages/Main';
import ErrorBoundary from './components/common/ErrorBoundary';
import useKeyboardShortcuts from './hooks/useKeyboardShortcuts';
import { useConversationActions } from './store/useConversationStore';

const queryClient = new QueryClient();

// This ID is hardcoded in ThreadList.jsx as well. Centralizing it here for now.
const MOCK_SUB_ROOM_ID = 'sub_room_123';

// New component to be able to use hooks that require Router context (like useNavigate)
function AppContent() {
  const [showSearch, setShowSearch] = useState(false);
  const { addThread } = useConversationActions();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Logic for creating a new thread, moved from ThreadList.jsx
  const createThreadMutation = useMutation({
    mutationFn: (newThread) => axios.post(`/api/convo/subrooms/${MOCK_SUB_ROOM_ID}/threads`, newThread),
    onSuccess: (response) => {
      const newThread = response.data;
      // Manually update the query cache to reflect the new thread immediately
      queryClient.setQueryData(['threads', MOCK_SUB_ROOM_ID], (oldData) => oldData ? [newThread, ...oldData] : [newThread]);
      addThread(newThread);
      navigate(`/threads/${newThread.id}`);
    },
  });

  const handleNewThread = () => {
    if (createThreadMutation.isPending) return;
    const title = "New Conversation";
    createThreadMutation.mutate({ title });
  };

  const handleSearch = () => setShowSearch(true);

  // Define the shortcuts and their handlers.
  // The useKeyboardShortcuts hook handles Ctrl/Cmd mapping.
  const shortcuts = {
    'Ctrl+N': handleNewThread,
    'Ctrl+K': handleSearch,
  };

  // Register the shortcuts globally
  useKeyboardShortcuts(shortcuts);

  return (
    // The AppProvider now gets the handleNewThread function to pass down via context
    <AppProvider value={{ handleNewThread, createThreadMutation }}>
      {showSearch && <SearchPanel onClose={() => setShowSearch(false)} />}
      <ErrorBoundary>
        <Routes>
          <Route path="/" element={<Main />} />
          <Route path="/threads/:threadId" element={<Main />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </ErrorBoundary>
    </AppProvider>
  );
}

// Main App component now sets up providers and the router
function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <AppContent />
      </Router>
    </QueryClientProvider>
  );
}

export default App;
