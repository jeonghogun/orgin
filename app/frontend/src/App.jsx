import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useParams, useNavigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';

import SearchPanel from './components/conversation/SearchPanel';
import { AppProvider } from './context/AppContext';
import Main from './pages/Main';
import ErrorBoundary from './components/common/ErrorBoundary';
import useKeyboardShortcuts from './hooks/useKeyboardShortcuts';
import { useConversationActions } from './store/useConversationStore';
import useRoomStore from './store/useRoomStore';

const queryClient = new QueryClient();

// This component uses hooks that require Router context (like useNavigate)
function AppContent() {
  const [showSearch, setShowSearch] = useState(false);
  const { addThread } = useConversationActions();
  const { selectedRoomId } = useRoomStore();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Logic for creating a new thread (conversation) in the selected room
  const createThreadMutation = useMutation({
    mutationFn: (newThread) => {
      if (!selectedRoomId) throw new Error("No room selected");
      // This API endpoint needs to be verified. Assuming a standard REST structure.
      return axios.post(`/api/rooms/${selectedRoomId}/threads`, newThread);
    },
    onSuccess: (response) => {
      const newThread = response.data;
      queryClient.invalidateQueries({ queryKey: ['threads', selectedRoomId] });
      addThread(newThread);
      navigate(`/rooms/${selectedRoomId}/threads/${newThread.id}`);
    },
    onError: (error) => {
      console.error('Failed to create thread:', error);
      alert('Could not create a new conversation in this room.');
    }
  });

  const handleNewThread = () => {
    if (createThreadMutation.isPending) return;
    const title = "New Conversation";
    createThreadMutation.mutate({ title });
  };

  const handleSearch = () => setShowSearch(true);

  // Copy/Paste functionality remains the same
  const handleCopy = () => {
    const selectedText = window.getSelection().toString();
    if (selectedText) {
      navigator.clipboard.writeText(selectedText).catch(err => console.error('Failed to copy text:', err));
    }
  };

  const handlePaste = () => {
    navigator.clipboard.readText().then(text => {
      const activeElement = document.activeElement;
      if (activeElement && (activeElement.tagName === 'INPUT' || activeElement.tagName === 'TEXTAREA')) {
        activeElement.value += text;
        activeElement.dispatchEvent(new Event('input', { bubbles: true }));
      }
    }).catch(err => console.error('Failed to paste text:', err));
  };

  // Simplified shortcuts
  const shortcuts = {
    'Ctrl+N': handleNewThread,
    'Ctrl+K': handleSearch,
    'Ctrl+C': handleCopy,
    'Ctrl+V': handlePaste,
  };

  useKeyboardShortcuts(shortcuts);

  return (
    <AppProvider value={{ handleNewThread, createThreadMutation }}>
      {showSearch && <SearchPanel onClose={() => setShowSearch(false)} />}
      <ErrorBoundary>
        <Routes>
          <Route path="/" element={<Main />} />
          <Route path="/rooms/:roomId" element={<Main />} />
          <Route path="/rooms/:roomId/threads/:threadId" element={<Main />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </ErrorBoundary>
    </AppProvider>
  );
}

// Main App component sets up providers and the router
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
