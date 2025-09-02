import React, { useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import useWebSocket from '../hooks/useWebSocket';

const fetchMessages = async (roomId) => {
  if (!roomId) return [];
  const { data } = await axios.get(`/api/rooms/${roomId}/messages`);
  return data || [];
};

const MessageList = ({ roomId }) => {
  const queryClient = useQueryClient();
  const messagesEndRef = useRef(null);

  const handleNewMessage = (newMessage) => {
    queryClient.setQueryData(['messages', roomId], (oldData) => {
      if (!oldData) return [newMessage];
      // Prevent duplicates
      if (oldData.some(msg => msg.message_id === newMessage.message_id)) {
        return oldData;
      }
      return [...oldData, newMessage];
    });
  };

  useWebSocket(roomId, handleNewMessage);

  const { data: messages = [], isLoading } = useQuery({
    queryKey: ['messages', roomId],
    queryFn: () => fetchMessages(roomId),
    enabled: !!roomId,
  });

  // 새 메시지가 올 때마다 자동으로 맨 아래로 스크롤
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (!roomId) {
    return (
      <div className="flex items-center justify-center h-full text-muted text-body">
        룸을 선택하여 대화를 시작하세요
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-muted">메시지를 불러오는 중...</div>
      </div>
    );
  }

  if (!messages || messages.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="text-muted mb-2">아직 메시지가 없습니다</div>
          <div className="text-meta text-muted">새로운 대화를 시작해보세요</div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {messages.map((message, index) => (
        <div key={message.id || index} className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
          {message.role === 'assistant' && (
            <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center text-white text-sm font-medium">
              A
            </div>
          )}
          
          <div className={`max-w-[70%] ${message.role === 'user' ? 'order-2' : 'order-1'}`}>
            <div className={`p-3 rounded-card ${
              message.role === 'user' 
                ? 'bg-accent text-white' 
                : 'bg-panel-elev border border-border text-text'
            }`}>
              <div className="text-body whitespace-pre-wrap">
                {message.isThinking ? (
                  <div className="flex items-center space-x-2">
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                  </div>
                ) : (
                  message.content
                )}
              </div>
            </div>
            <div className={`text-meta text-muted mt-1 ${
              message.role === 'user' ? 'text-right' : 'text-left'
            }`}>
              {new Date(message.timestamp || Date.now()).toLocaleTimeString('ko-KR', {
                hour: '2-digit',
                minute: '2-digit'
              })}
            </div>
          </div>

          {message.role === 'user' && (
            <div className="w-8 h-8 rounded-full bg-accent-weak flex items-center justify-center text-white text-sm font-medium order-1">
              U
            </div>
          )}
        </div>
      ))}
      
      {/* 자동 스크롤을 위한 참조 요소 */}
      <div ref={messagesEndRef} />
    </div>
  );
};

export default MessageList;
