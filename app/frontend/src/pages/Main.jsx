import React, { useState, useEffect } from 'react';
import RoomHeader from '../components/RoomHeader';
import MessageList from '../components/MessageList';
import ChatInput from '../components/ChatInput';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { useAppContext } from '../context/AppContext';

const Main = ({ roomId }) => {
  const { handleToggleReview } = useAppContext();
  const [suggestions, setSuggestions] = useState([]);

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

  // 검토 시작 버튼 클릭 핸들러
  const handleStartReview = () => {
    if (roomData) {
      handleToggleReview(roomData);
    }
  };

  // 제안사항 (예시)
  useEffect(() => {
    if (roomId) {
      setSuggestions([
        "이 주제에 대해 더 자세히 설명해주세요",
        "관련 예시를 들어주세요",
        "실용적인 적용 방법을 알려주세요"
      ]);
    }
  }, [roomId]);

  return (
    <div className="flex flex-col h-full bg-bg">
      {/* 헤더 - 고정 */}
      <RoomHeader
        title={roomData?.name || "새 채팅"}
        subtitle={roomData?.description || "새로운 대화를 시작하세요"}
        actions={
          roomData && (
            <button
              onClick={handleStartReview}
              className="btn-primary text-body px-4 py-2 rounded-button"
            >
              검토 시작
            </button>
          )
        }
      />

      {/* 메시지 목록 - 스크롤 가능, 입력창 위 공간 확보 */}
      <div className="flex-1 overflow-y-auto px-4 pb-4">
        {roomId ? (
          <>
            <MessageList roomId={roomId} />
            
            {/* 제안사항 */}
            {suggestions.length > 0 && (
              <div className="mt-6 space-y-2">
                <h3 className="text-h2 text-text mb-3">제안사항</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {suggestions.map((suggestion, index) => (
                    <button
                      key={index}
                      className="p-3 text-left bg-panel border border-border rounded-card hover:bg-panel-elev transition-colors duration-150 text-body"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="text-h1 text-text mb-4">룸을 선택하여 대화를 시작하세요</div>
              <div className="text-body text-muted">왼쪽 사이드바에서 채팅방을 선택하거나 새 채팅을 시작하세요</div>
            </div>
          </div>
        )}
      </div>

      {/* 채팅 입력창 - 항상 하단 고정 */}
      <div className="border-t border-border bg-panel p-4">
        <ChatInput roomId={roomId} disabled={!roomId} />
      </div>
    </div>
  );
};

export default Main;
