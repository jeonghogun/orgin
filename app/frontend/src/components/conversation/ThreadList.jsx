import React, { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { useThreads, useConversationActions } from '../../store/useConversationStore';
import { PlusIcon, ChatBubbleLeftIcon, ArrowDownTrayIcon } from '@heroicons/react/24/outline';
import BudgetDisplay from './BudgetDisplay';

const ThreadList = ({ isLoading, error }) => {
  const threads = useThreads();
  const { addThread } = useConversationActions();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { threadId: currentThreadId } = useParams();
  const [exportJobs, setExportJobs] = useState({});

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

  const exportThreadMutation = useMutation({
    mutationFn: ({ threadId, format }) => 
      axios.post(`/api/convo/threads/${threadId}/export/jobs?format=${format}`),
    onSuccess: (response, variables) => {
      const { jobId } = response.data;
      setExportJobs(prev => ({
        ...prev,
        [variables.threadId]: { jobId, status: 'processing', format: variables.format }
      }));
      
      // Start polling for job status
      pollExportJob(variables.threadId, jobId);
    },
  });

  const pollExportJob = async (threadId, jobId) => {
    const pollInterval = setInterval(async () => {
      try {
        const response = await axios.get(`/api/export/jobs/${jobId}`);
        const job = response.data;
        
        setExportJobs(prev => ({
          ...prev,
          [threadId]: { ...prev[threadId], status: job.status }
        }));
        
        if (job.status === 'done' || job.status === 'failed') {
          clearInterval(pollInterval);
          if (job.status === 'done' && job.file_url) {
            // Trigger download
            window.open(`/api/export/jobs/${jobId}/download`, '_blank');
          }
        }
      } catch (error) {
        console.error('Error polling export job:', error);
        clearInterval(pollInterval);
      }
    }, 2000);
  };

  const handleExportThread = (threadId, format = 'zip') => {
    exportThreadMutation.mutate({ threadId, format });
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
          {threads.map((thread) => {
            const exportJob = exportJobs[thread.id];
            return (
              <div
                key={thread.id}
                className={`flex items-center space-x-2 p-2 rounded-md text-sm font-medium group ${
                  thread.id === currentThreadId
                    ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-white'
                    : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                }`}
              >
                <Link
                  to={`/threads/${thread.id}`}
                  className="flex items-center space-x-3 flex-1 min-w-0"
                >
                  <ChatBubbleLeftIcon className="h-5 w-5 flex-shrink-0" />
                  <span className="truncate">{thread.title}</span>
                </Link>
                <button
                  onClick={(e) => {
                    e.preventDefault();
                    handleExportThread(thread.id, 'zip');
                  }}
                  disabled={exportJob?.status === 'processing'}
                  className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50"
                  title="Export conversation"
                >
                  {exportJob?.status === 'processing' ? (
                    <div className="h-4 w-4 border-2 border-gray-300 border-t-blue-500 rounded-full animate-spin" />
                  ) : (
                    <ArrowDownTrayIcon className="h-4 w-4" />
                  )}
                </button>
              </div>
            );
          })}
        </nav>
      </div>
      <div className="p-2 border-t border-gray-200 dark:border-gray-700">
        <BudgetDisplay />
      </div>
    </div>
  );
};

export default ThreadList;
