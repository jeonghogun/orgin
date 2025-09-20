import React, { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import ChatView from '../components/conversation/ChatView';
import MessageList from '../components/MessageList';
import useRoomsQuery from '../hooks/useRoomsQuery';
import { ROOM_TYPES } from '../constants';

const Main = () => {
  const { threadId, roomId } = useParams();
  const navigate = useNavigate();

  const { data: rooms = [] } = useRoomsQuery();

  const currentRoom = rooms.find(room => room.room_id === roomId);

  useEffect(() => {
    if (rooms.length === 0 || roomId) {
      return;
    }
    const mainRoom = rooms.find((room) => room.type === ROOM_TYPES.MAIN);
    if (mainRoom) {
      navigate(`/rooms/${mainRoom.room_id}`, { replace: true });
    }
  }, [rooms, roomId, navigate]);

  return (
    <div className="flex h-screen bg-bg text-text">
      <div className="fixed top-0 left-0 h-full">
        <Sidebar />
      </div>

      {/* The ThreadList and ChatView are now separate from the Sidebar flow */}
      {/* It's assumed that selecting a room in the Sidebar will then populate the ThreadList */}
      <div className="flex-1 flex flex-col h-screen ml-72">
          {/* The main chat view takes the rest of the space */}
          <main className="flex-1 flex flex-col h-screen">
              <div className="flex-1 overflow-y-auto">
                  {threadId && roomId ? (
                      <ChatView key={threadId} threadId={threadId} currentRoom={currentRoom} />
                  ) : roomId ? (
                      <MessageList roomId={roomId} currentRoom={currentRoom} />
                  ) : (
                      <div className="flex items-center justify-center h-full">
                          <div className="text-center">
                              <h2 className="text-h2">Select a Room</h2>
                              <p className="text-muted">
                                  Choose a room from the sidebar to start chatting.
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
