import React, { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { useParams } from 'react-router-dom';

import { useConversationActions } from '../store/useConversationStore';
import ThreadList from '../components/conversation/ThreadList';
import ChatView from '../components/conversation/ChatView';
import BudgetDisplay from '../components/conversation/BudgetDisplay';

const Main = () => {
  const { threadId } = useParams();
  const { setThreads } = useConversationActions();

  // For now, let's assume the concept of a "sub-room" is static.
  const MOCK_SUB_ROOM_ID = 'sub_room_123';

  const { data: threads, isLoading, error } = useQuery({
    queryKey: ['threads', MOCK_SUB_ROOM_ID],
    queryFn: async () => {
      const { data } = await axios.get(`/api/convo/subrooms/${MOCK_SUB_ROOM_ID}/threads`);
      return data;
    },
    onSuccess: (data) => {
      setThreads(data);
    },
    enabled: !!MOCK_SUB_ROOM_ID,
  });

  return (
    <div className="flex h-screen bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
      <div className="fixed top-0 left-0 h-full">
        <ThreadList
          isLoading={isLoading}
          error={error}
        />
      </div>

      <main className="flex-1 flex flex-col h-screen ml-72">
        <div className="p-2 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
          <BudgetDisplay />
        </div>
        <div className="flex-1 overflow-y-auto">
          {threadId ? (
            <ChatView key={threadId} threadId={threadId} />
          ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <h2 className="text-2xl font-semibold">Select a conversation</h2>
              <p className="text-gray-500">Choose a conversation from the list, or start a new one.</p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default Main;
