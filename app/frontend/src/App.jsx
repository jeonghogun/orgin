import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useParams, useNavigate, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useMutation, useQueryClient, useQuery } from '@tanstack/react-query';
import axios from 'axios';

import SearchPanel from './components/conversation/SearchPanel';
import { AppProvider } from './context/AppContext';
import Main from './pages/Main';
import ErrorBoundary from './components/common/ErrorBoundary';
import useKeyboardShortcuts from './hooks/useKeyboardShortcuts';
import toast from 'react-hot-toast';
import { addThread } from './store/useConversationStore';
import { ROOM_TYPES } from './constants';

// This component uses hooks that require Router context (like useNavigate)
import GlobalSearchModal from './components/search/GlobalSearchModal';

function AppContent() {
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { roomId, threadId } = useParams();
  const location = useLocation();

  // 룸 목록을 가져와서 메인룸 자동 선택
  const { data: rooms = [] } = useQuery({
    queryKey: ['rooms'],
    queryFn: async () => {
      const { data } = await axios.get('/api/rooms');
      return data;
    },
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  // 메인룸 자동 선택 로직 - 루트 경로에서만 실행
  useEffect(() => {
    if (rooms.length > 0 && !roomId && location.pathname === '/') {
      const mainRoom = rooms.find(room => room.type === ROOM_TYPES.MAIN);
      if (mainRoom) {
        navigate(`/rooms/${mainRoom.room_id}`);
      }
    }
  }, [rooms, roomId, location.pathname, navigate]);

  // Logic for creating a new thread (conversation) in the selected room
  const createThreadMutation = useMutation({
    mutationFn: ({ roomId, title }) => {
      if (!roomId) throw new Error("No room selected");
      return axios.post(`/api/convo/rooms/${roomId}/threads`, { title });
    },
    onSuccess: (response, { roomId }) => {
      const newThread = response.data;
      queryClient.invalidateQueries({ queryKey: ['threads', roomId] });
      addThread(newThread);
      navigate(`/rooms/${roomId}/threads/${newThread.id}`);
    },
    onError: (error) => {
      console.error('Failed to create thread:', error);
      toast.error('Could not create a new conversation in this room.');
    }
  });

  const handleNewThread = () => {
    if (createThreadMutation.isPending || !roomId) return;
    createThreadMutation.mutate({ roomId, title: "New Conversation" });
  };
  


  const handleSearch = () => setIsSearchOpen(true);

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
    'Meta+K': handleSearch, // Using Meta for Cmd key on Mac
    'Ctrl+K': handleSearch,
    'Ctrl+C': handleCopy,
    'Ctrl+V': handlePaste,
  };

  useKeyboardShortcuts(shortcuts);

  // 룸 생성 mutation 추가
  return (
    <AppProvider value={{ handleNewThread, createThreadMutation }}>
      {isSearchOpen && <GlobalSearchModal onClose={() => setIsSearchOpen(false)} />}
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

// App component is now simpler, as providers are in main.jsx
function App() {
  return <AppContent />;
}

export default App;
