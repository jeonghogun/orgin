import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';

import apiClient from '../../lib/apiClient';
import LoadingSpinner from '../common/LoadingSpinner';
import ErrorMessage from '../common/ErrorMessage';

const searchHybrid = async (query) => {
  if (!query || query.length < 3) {
    return []; // Don't search for very short queries
  }
  const { data } = await apiClient.get(`/api/search/hybrid?q=${query}`);
  return data.data.results;
};

const GlobalSearchModal = ({ onClose }) => {
  const [query, setQuery] = useState('');

  const { data: results, error, isLoading, refetch } = useQuery({
    queryKey: ['hybridSearch', query],
    queryFn: () => searchHybrid(query),
    enabled: false, // Only fetch when manually triggered
  });

  useEffect(() => {
    const handler = setTimeout(() => {
      if (query.length >= 3) {
        refetch();
      }
    }, 500); // Debounce search by 500ms

    return () => {
      clearTimeout(handler);
    };
  }, [query, refetch]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-start justify-center pt-20">
      <div className="bg-panel-elevated rounded-lg shadow-xl w-full max-w-2xl">
        <div className="p-4 border-b border-border">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search across all conversations and documents..."
            className="w-full bg-transparent text-lg outline-none"
            autoFocus
          />
        </div>
        <div className="p-4 max-h-[60vh] overflow-y-auto">
          {isLoading && <LoadingSpinner />}
          {error && <ErrorMessage error={error} message="Search failed." />}
          {!isLoading && !error && results && (
            <ul>
              {results.map((result) => (
                <li key={result.id} className="p-2 border-b border-border hover:bg-panel">
                  <p className="font-semibold">{result.content}</p>
                  <p className="text-sm text-muted">
                    Source: {result.source} | Score: {result.score.toFixed(2)}
                  </p>
                </li>
              ))}
            </ul>
          )}
          {!isLoading && query.length > 0 && results?.length === 0 && (
            <p className="text-center text-muted">No results found.</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default GlobalSearchModal;
