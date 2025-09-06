import React, { useState, useEffect, useMemo } from 'react';
import { useThreads, useMessages } from '../../store/useConversationStore';

const SearchPanel = ({ onClose }) => {
  const [query, setQuery] = useState('');
  const allThreads = useThreads();
  // This is inefficient for large stores, but fine for a demo.
  // A real implementation would use a server-side search API.
  const allMessagesByThread = useConversationStore((state) => state.messagesByThread);

  const searchResults = useMemo(() => {
    if (!query.trim()) return [];

    const lowerCaseQuery = query.toLowerCase();
    const results = [];

    // Search threads
    allThreads.forEach(thread => {
      if (thread.title.toLowerCase().includes(lowerCaseQuery)) {
        results.push({ type: 'thread', item: thread, text: thread.title });
      }
    });

    // Search messages
    Object.values(allMessagesByThread).flat().forEach(message => {
        if (message.content.toLowerCase().includes(lowerCaseQuery)) {
            results.push({ type: 'message', item: message, text: message.content });
        }
    });

    return results.slice(0, 20); // Limit results
  }, [query, allThreads, allMessagesByThread]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 pt-20">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl flex flex-col">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search conversations..."
          className="w-full p-4 bg-transparent border-b dark:border-gray-700 focus:ring-0 text-lg"
          autoFocus
        />
        <div className="max-h-96 overflow-y-auto">
          {searchResults.length === 0 && query && (
            <div className="p-4 text-center text-gray-500">No results found.</div>
          )}
          <ul>
            {searchResults.map(({ type, item, text }, index) => (
              <li key={`${type}-${item.id}-${index}`} className="p-4 border-b dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer">
                <p className="font-semibold text-sm">{type === 'thread' ? `Thread: ${item.title}` : `Message in ${item.thread_id}`}</p>
                <p className="text-xs text-gray-600 dark:text-gray-400 truncate">{text}</p>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
};

export default SearchPanel;
