import React, { useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { useThreads, setThreads } from '../../store/useConversationStore';
import { useAppContext } from '../../context/AppContext';
import { PlusIcon, ChatBubbleLeftIcon } from '@heroicons/react/24/outline';

const ThreadList = () => {
  const threads = useThreads();
  const { handleNewThread, createThreadMutation } = useAppContext();
  const { threadId: currentThreadId, roomId: selectedRoomId } = useParams();

  const { data, isLoading, error } = useQuery({
    queryKey: ['threads', selectedRoomId],
    queryFn: async () => {
      const { data } = await axios.get(`/api/convo/rooms/${selectedRoomId}/threads`);
      return data;
    },
    onSuccess: (data) => {
      setThreads(data);
    },
    enabled: !!selectedRoomId,
  });

  useEffect(() => {
    if (data) {
        setThreads(data);
    }
  }, [data, setThreads]);

  if (!selectedRoomId) {
    return (
      <div className="p-4 text-center text-muted">
        <p>Select a room to see conversations.</p>
      </div>
    );
  }

  return (
    <div className="h-full bg-panel flex flex-col">
      <div className="p-4 border-b border-border">
        <h2 className="text-h2">Conversations</h2>
      </div>

      <div className="flex-1 overflow-y-auto">
        {isLoading && <div className="p-4 text-muted">Loading threads...</div>}
        {error && <div className="p-4 text-danger">Error loading threads.</div>}
        <nav className="p-2 space-y-1">
          {threads && threads.length > 0 ? (
            threads.map((thread) => (
              <Link
                key={thread.id}
                to={`/rooms/${selectedRoomId}/threads/${thread.id}`}
                className={`flex items-center space-x-3 p-2 rounded-lg text-sm font-medium group ${
                  thread.id === currentThreadId
                    ? 'bg-accent text-white'
                    : 'text-text hover:bg-panel-elev'
                }`}
              >
                <ChatBubbleLeftIcon className="h-5 w-5 flex-shrink-0" />
                <span className="truncate">{thread.title}</span>
              </Link>
            ))
          ) : null}
        </nav>
      </div>
    </div>
  );
};

export default ThreadList;
