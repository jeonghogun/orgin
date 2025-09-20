import React from 'react';
import RoomHeader from '../components/RoomHeader';
import MessageList from '../components/MessageList';
import ChatInput from '../components/ChatInput';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../lib/apiClient';
import { useAppContext } from '../context/AppContext';

const Sub = ({ roomId, onToggleReview, createRoomMutation }) => {
  const { sidebarOpen } = useAppContext();
  
  // 룸 정보 조회
  const { data: roomData } = useQuery({
    queryKey: ['room', roomId],
    queryFn: async () => {
      if (!roomId) return null;
      const response = await apiClient.get(`/api/rooms/${roomId}`);
      return response.data;
    },
    enabled: !!roomId,
  });

  return (
    <div className="flex flex-col h-full bg-bg relative overflow-hidden">
      {/* 헤더 - 고정 */}
      <div className="flex-shrink-0 z-10">
        <RoomHeader
          title={roomData?.name || "세부 룸"}
          subtitle={roomData?.description || "세부 대화"}
          showBackButton={true}
          actions={
            roomData && (
              <button
                onClick={() => onToggleReview(roomData)}
                className="btn-primary text-body px-4 py-2 rounded-button"
              >
                검토 시작
              </button>
            )
          }
        />
      </div>

      {/* 메시지 목록 - 독립적인 스크롤 영역 */}
      <div className="flex-1 overflow-y-auto px-4 pb-20 min-h-0">
          <div className="max-w-3xl mx-auto">
            <MessageList
              roomId={roomId}
              currentRoom={roomData}
              createRoomMutation={createRoomMutation}
            />
          </div>
        </div>

      {/* 채팅 입력창 - 화면 전체 하단에 고정 */}
      <div 
        className="fixed bottom-0 border-t border-border bg-panel p-4 z-20 transition-all duration-150"
        style={{ 
          left: sidebarOpen ? '280px' : '0px', 
          right: '0px' 
        }}
      >
        <div className="max-w-3xl mx-auto">
            <ChatInput
              roomId={roomId}
              roomData={roomData}
              createRoomMutation={createRoomMutation}
            />
          </div>
        </div>
    </div>
  );
};

export default Sub;
