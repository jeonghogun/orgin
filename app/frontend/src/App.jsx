import React, { useState } from 'react';
import { Routes, Route, Navigate, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';

import SearchPanel from './components/conversation/SearchPanel';
import { AppProvider } from './context/AppContext';
import Main from './pages/Main';
import ErrorBoundary from './components/common/ErrorBoundary';
import useKeyboardShortcuts from './hooks/useKeyboardShortcuts';
import { useConversationActions } from './store/useConversationStore';
import { ROOM_TYPES } from './constants';

// This ID is hardcoded in ThreadList.jsx as well. Centralizing it here for now.
const MOCK_SUB_ROOM_ID = 'sub_room_123';

// New component to be able to use hooks that require Router context (like useNavigate)
function AppContent() {
  const [showSearch, setShowSearch] = useState(false);
  const [copiedText, setCopiedText] = useState('');
  const { addThread } = useConversationActions();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { threadId } = useParams();

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

  // New room creation logic (similar to Sidebar.jsx)
  const createRoomMutation = useMutation({
    mutationFn: async ({ name, type, parentId }) => {
      const { data } = await axios.post('/api/rooms', { name, type, parent_id: parentId });
      return data;
    },
    onSuccess: (newRoom) => {
      queryClient.invalidateQueries({ queryKey: ['rooms'] });
      navigate(`/rooms/${newRoom.room_id}`);
    },
    onError: (error) => {
      console.error('룸 생성에 실패했습니다:', error);
    },
  });

  const handleNewRoom = () => {
    const roomName = prompt('새 룸의 이름을 입력하세요:', '새 룸');
    if (roomName && roomName.trim()) {
      createRoomMutation.mutate({ 
        name: roomName.trim(), 
        type: ROOM_TYPES.SUB, 
        parentId: null // Create as root room
      });
    }
  };

  // Copy/Paste functionality
  const handleCopy = () => {
    // Get selected text from the page
    const selectedText = window.getSelection().toString();
    if (selectedText) {
      navigator.clipboard.writeText(selectedText).then(() => {
        setCopiedText(selectedText);
        console.log('Text copied to clipboard:', selectedText);
      }).catch(err => {
        console.error('Failed to copy text:', err);
      });
    } else {
      console.log('No text selected to copy');
    }
  };

  const handlePaste = () => {
    navigator.clipboard.readText().then(text => {
      if (text) {
        // Find active input/textarea and paste text
        const activeElement = document.activeElement;
        if (activeElement && (activeElement.tagName === 'INPUT' || activeElement.tagName === 'TEXTAREA')) {
          const start = activeElement.selectionStart;
          const end = activeElement.selectionEnd;
          const currentValue = activeElement.value;
          const newValue = currentValue.substring(0, start) + text + currentValue.substring(end);
          
          activeElement.value = newValue;
          activeElement.setSelectionRange(start + text.length, start + text.length);
          
          // Trigger input event to update React state
          const event = new Event('input', { bubbles: true });
          activeElement.dispatchEvent(event);
        }
        console.log('Text pasted from clipboard:', text);
      }
    }).catch(err => {
      console.error('Failed to paste text:', err);
    });
  };

  // Define the shortcuts and their handlers.
  // The useKeyboardShortcuts hook handles Ctrl/Cmd mapping.
  const shortcuts = {
    'Ctrl+N': handleNewThread,
    'Ctrl+K': handleSearch,
    'Ctrl+Shift+N': handleNewRoom,
    'Ctrl+C': handleCopy,
    'Ctrl+V': handlePaste,
  };

  // Register the shortcuts globally
  useKeyboardShortcuts(shortcuts);

  return (
    // The AppProvider now gets the handleNewThread function to pass down via context
    <AppProvider value={{ handleNewThread, createThreadMutation, handleNewRoom, handleCopy, handlePaste, createRoomMutation, threadId }}>
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

// Main App component now simply renders AppContent
function App() {
  return <AppContent />;
}

export default App;
