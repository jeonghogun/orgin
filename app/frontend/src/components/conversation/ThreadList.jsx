import React from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { useThreads, useConversationActions } from '../../store/useConversationStore';
import { PlusIcon, ChatBubbleLeftIcon } from '@heroicons/react/24/outline';
import BudgetDisplay from './BudgetDisplay';

const ThreadList = ({ isLoading, error }) => {
  const threads = useThreads();
  const { addThread } = useConversationActions();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { threadId: currentThreadId } = useParams();

  const MOCK_SUB_ROOM_ID = 'sub_room_123';

  const createThreadMutation = useMutation({
    mutationFn: (newThread) => axios.post(`/api/convo/subrooms/${MOCK_SUB_ROOM_ID}/threads`, newThread),
    onSuccess: (response) => {
      const newThread = response.data;
      addThread(newThread);
      navigate(`/threads/${newThread.id}`);
    },
  });

  const handleNewThread = () => {
    const title = "New Conversation"; // Simple title for now
    createThreadMutation.mutate({ title });
  };

  return (
    <div className="w-72 h-screen bg-gray-50 dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 flex flex-col">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
        <h2 className="text-lg font-semibold">Conversations</h2>
        <button
          onClick={handleNewThread}
          disabled={createThreadMutation.isPending}
          className="p-2 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-50"
        >
          <PlusIcon className="h-6 w-6" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {isLoading && <div className="p-4">Loading...</div>}
        {error && <div className="p-4 text-red-500">Error.</div>}
        <nav className="p-2 space-y-1">
          {threads.map((thread) => (
            <Link
              key={thread.id}
              to={`/threads/${thread.id}`}
              className={`flex items-center space-x-3 p-2 rounded-md text-sm font-medium ${
                thread.id === currentThreadId
                  ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-white'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
              }`}
            >
              <ChatBubbleLeftIcon className="h-5 w-5" />
              <span className="truncate flex-1">{thread.title}</span>
            </Link>
          ))}
        </nav>
      </div>
      <div className="p-2 border-t border-gray-200 dark:border-gray-700">
        <BudgetDisplay />
      </div>
    </div>
  );
};

export default ThreadList;
