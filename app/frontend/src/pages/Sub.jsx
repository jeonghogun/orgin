import React from 'react';
import RoomHeader from '../components/RoomHeader';
import MessageList from '../components/MessageList';
import ChatInput from '../components/ChatInput';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

const Sub = ({ roomId, onToggleReview }) => {
  // 룸 정보 조회
  const { data: roomData } = useQuery({
    queryKey: ['room', roomId],
    queryFn: async () => {
      if (!roomId) return null;
      const response = await axios.get(`/api/rooms/${roomId}`);
      return response.data;
    },
    enabled: !!roomId,
  });

  return (
    <div className="flex flex-col h-full bg-bg">
      {/* 헤더 - 고정 */}
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

      {/* 메시지 목록 - 스크롤 가능, 입력창 위 공간 확보 */}
      <div className="flex-1 overflow-y-auto px-4 pb-4">
        <MessageList roomId={roomId} />
      </div>

      {/* 채팅 입력창 - 항상 하단 고정 */}
      <div className="border-t border-border bg-panel p-4">
        <ChatInput roomId={roomId} />
      </div>
    </div>
  );
};

export default Sub;
