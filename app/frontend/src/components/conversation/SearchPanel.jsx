import React, { useState, useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../../lib/apiClient';
import { useThreads } from '../../store/useConversationStore';

const SearchPanel = ({ onClose, currentThreadId = null }) => {
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const allThreads = useThreads();

  // Debounced search
  useEffect(() => {
    if (!query.trim()) {
      setSearchResults([]);
      return;
    }

    const timeoutId = setTimeout(async () => {
      setIsSearching(true);
      try {
        const response = await apiClient.post('/api/convo/search', {
          query: query.trim(),
          thread_id: currentThreadId,
          limit: 20,
          include_attachments: true
        });
        setSearchResults(response.data.results || []);
      } catch (error) {
        console.error('Search error:', error);
        setSearchResults([]);
      } finally {
        setIsSearching(false);
      }
    }, 300);

    return () => clearTimeout(timeoutId);
  }, [query, currentThreadId]);

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
          {isSearching && (
            <div className="p-4 text-center text-gray-500">Searching...</div>
          )}
          {!isSearching && searchResults.length === 0 && query && (
            <div className="p-4 text-center text-gray-500">No results found.</div>
          )}
          {!isSearching && searchResults.length > 0 && (
            <ul>
              {searchResults.map((result, index) => (
                <li key={`${result.source}-${result.message_id}-${index}`} 
                    className="p-4 border-b dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer">
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <p className="font-semibold text-sm">
                        {result.source === 'message' ? 
                          `${result.role === 'user' ? 'User' : 'Assistant'} message` : 
                          'Attachment content'
                        }
                      </p>
                      <p className="text-xs text-gray-600 dark:text-gray-400 truncate mt-1">
                        {result.content}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        Thread: {result.thread_id} • Score: {result.relevance_score.toFixed(3)}
                      </p>
                    </div>
                    <div className="ml-2">
                      <span className={`px-2 py-1 rounded-full text-xs ${
                        result.source === 'message' 
                          ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
                          : 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                      }`}>
                        {result.source}
                      </span>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
};

export default SearchPanel;
