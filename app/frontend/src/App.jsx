import React, { useState } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';

import { AppProvider } from './context/AppContext';
import Main from './pages/Main';
import ErrorBoundary from './components/common/ErrorBoundary';
import useKeyboardShortcuts from './hooks/useKeyboardShortcuts';

// This component uses hooks that require Router context (like useNavigate)
import GlobalSearchModal from './components/search/GlobalSearchModal';

function AppContent() {
  const [isSearchOpen, setIsSearchOpen] = useState(false);

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
    'Meta+K': handleSearch, // Using Meta for Cmd key on Mac
    'Ctrl+K': handleSearch,
    'Ctrl+C': handleCopy,
    'Ctrl+V': handlePaste,
  };

  useKeyboardShortcuts(shortcuts);

  return (
    <AppProvider>
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
