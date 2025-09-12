import React from 'react';
import { useParams } from 'react-router-dom';
import Sidebar from '../components/sidebar/Sidebar';
import ThreadList from '../components/conversation/ThreadList';
import ChatView from '../components/conversation/ChatView';
import BudgetDisplay from '../components/conversation/BudgetDisplay';
import useRoomStore from '../store/useRoomStore';

const Main = () => {
  const { threadId } = useParams();
  const { selectedRoomId } = useRoomStore();

  return (
    <div className="flex h-screen bg-bg text-text">
      <div className="fixed top-0 left-0 h-full">
        <Sidebar />
      </div>

      {/* The ThreadList and ChatView are now separate from the Sidebar flow */}
      {/* It's assumed that selecting a room in the Sidebar will then populate the ThreadList */}
      <div className="flex-1 flex flex-col h-screen ml-72">
          {/* This section now shows the list of threads for the selected room */}
          <div className="w-80 border-r border-border flex flex-col">
              <ThreadList />
          </div>

          {/* The main chat view takes the rest of the space */}
          <main className="flex-1 flex flex-col h-screen">
              <div className="p-2 border-b border-border bg-panel">
                  <BudgetDisplay />
              </div>
              <div className="flex-1 overflow-y-auto">
                  {threadId && selectedRoomId ? (
                      <ChatView key={threadId} threadId={threadId} />
                  ) : (
                      <div className="flex items-center justify-center h-full">
                          <div className="text-center">
                              <h2 className="text-h2">Select a Conversation</h2>
                              <p className="text-muted">
                                  {selectedRoomId
                                      ? "Choose a conversation from the list or start a new one."
                                      : "Choose a room from the sidebar to see conversations."}
                              </p>
                          </div>
                      </div>
                  )}
              </div>
          </main>
      </div>
    </div>
  );
};

export default Main;
