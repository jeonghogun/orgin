import React, { useEffect } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useThreads, setThreads, addThread } from '../../store/useConversationStore';
import useKeyboardShortcuts from '../../hooks/useKeyboardShortcuts';
import { PlusIcon, ChatBubbleLeftIcon } from '@heroicons/react/24/outline';

const ThreadList = () => {
  const threads = useThreads();
  const { threadId: currentThreadId, roomId: selectedRoomId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const createThreadMutation = useMutation({
    mutationFn: async ({ roomId, title }) => {
      if (!roomId) throw new Error('No room selected');
      const { data } = await axios.post(`/api/convo/rooms/${roomId}/threads`, { title });
      return data;
    },
    onSuccess: (newThread, { roomId }) => {
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
    if (!selectedRoomId || createThreadMutation.isPending) return;
    createThreadMutation.mutate({ roomId: selectedRoomId, title: 'New Conversation' });
  };

  useKeyboardShortcuts({ 'Ctrl+N': handleNewThread });

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
      <div className="p-4 border-b border-border flex items-center justify-between">
        <h2 className="text-h2">Conversations</h2>
        <button
          type="button"
          onClick={handleNewThread}
          disabled={!selectedRoomId || createThreadMutation.isPending}
          className="inline-flex items-center justify-center rounded-md bg-accent px-2 py-1 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50"
          aria-label="Start a new conversation"
        >
          <PlusIcon className="h-5 w-5" />
        </button>
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
