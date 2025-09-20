import React, { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import ChatView from '../components/conversation/ChatView';
import MessageList from '../components/MessageList';
import Review from './Review';
import useRoomsQuery from '../hooks/useRoomsQuery';
import { ROOM_TYPES } from '../constants';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorMessage from '../components/common/ErrorMessage';
import EmptyState from '../components/common/EmptyState';

const Main = () => {
  const { threadId, roomId } = useParams();
  const navigate = useNavigate();

  const {
    data: rooms = [],
    isLoading,
    error,
  } = useRoomsQuery();

  const currentRoom = rooms.find(room => room.room_id === roomId);

  useEffect(() => {
    if (rooms.length === 0) {
      return;
    }
    
    // If roomId exists but room is not found, redirect to main room
    if (roomId && !currentRoom) {
      const mainRoom = rooms.find((room) => room.type === ROOM_TYPES.MAIN);
      if (mainRoom) {
        navigate(`/rooms/${mainRoom.room_id}`, { replace: true });
      }
      return;
    }
    
    // If no roomId, redirect to main room
    if (!roomId) {
      const mainRoom = rooms.find((room) => room.type === ROOM_TYPES.MAIN);
      if (mainRoom) {
        navigate(`/rooms/${mainRoom.room_id}`, { replace: true });
      }
    }
  }, [rooms, roomId, currentRoom, navigate]);

  const renderMainContent = () => {
    if (isLoading) {
      return <LoadingSpinner />;
    }

    if (error) {
      return (
        <ErrorMessage
          error={error}
          message="룸 정보를 불러오지 못했습니다. 좌측 상단 새로고침 버튼으로 다시 시도하세요."
        />
      );
    }

    if (!rooms.length) {
      return (
        <EmptyState
          heading="첫 번째 룸을 만들어 대화를 시작하세요"
          message="협업을 시작하려면 좌측 사이드바에서 ‘새 룸’ 버튼을 눌러보세요."
          icon="💡"
          tips={[
            '룸은 주제별로 대화를 모아 관리할 수 있게 도와줍니다.',
            '파일을 첨부하거나 요약 기능을 사용해 논의 흐름을 빠르게 정리해보세요.',
          ]}
        />
      );
    }

    if (currentRoom?.type === ROOM_TYPES.REVIEW) {
      return <Review key={currentRoom.room_id} roomId={currentRoom.room_id} />;
    }

    if (threadId && roomId) {
      return <ChatView key={threadId} threadId={threadId} currentRoom={currentRoom} />;
    }

    if (roomId) {
      return <MessageList roomId={roomId} currentRoom={currentRoom} />;
    }

    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <h2 className="text-h2">Select a Room</h2>
          <p className="text-muted">
            Choose a room from the sidebar to start chatting.
          </p>
        </div>
      </div>
    );
  };

  return (
    <div className="flex h-screen bg-bg text-text">
      <div className="fixed top-0 left-0 h-full">
        <Sidebar />
      </div>

      <div className="flex-1 flex flex-col h-screen ml-72">
        <main className="flex-1 flex flex-col h-screen">
          <div className="flex-1 overflow-y-auto">
            {renderMainContent()}
          </div>
        </main>
      </div>
    </div>
  );
};

export default Main;
