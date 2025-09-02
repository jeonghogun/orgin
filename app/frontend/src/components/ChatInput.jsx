import React, { useState, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';

const sendMessage = async ({ roomId, content, intent }) => {
  const payload = { content };
  if (intent) {
    payload.intent = intent;
  }
  const { data } = await axios.post(`/api/rooms/${roomId}/messages`, payload);
  return data.data;
};

const uploadFile = async ({ roomId, file }) => {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await axios.post(`/api/rooms/${roomId}/upload`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return data;
};

import { useAppContext } from '../context/AppContext';

const ChatInput = ({ roomId, disabled = false }) => {
  const [message, setMessage] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef(null);
  const queryClient = useQueryClient();
  const { showError } = useAppContext();

  const messageMutation = useMutation({
    mutationFn: sendMessage,
    onMutate: async (newMessage) => {
      setMessage(''); // 입력 필드 즉시 비우기
      await queryClient.cancelQueries({ queryKey: ['messages', roomId] });
      const previousMessages = queryClient.getQueryData(['messages', roomId]);

      const optimisticUserMessage = {
        id: `temp-user-${Date.now()}`,
        role: 'user',
        content: newMessage.content,
        timestamp: new Date().toISOString(),
      };

      const optimisticThinkingMessage = {
        id: `temp-assistant-${Date.now()}`,
        role: 'assistant',
        content: '생각 중...',
        timestamp: new Date().toISOString(),
        isThinking: true, // 로딩 상태 식별자
      };

      queryClient.setQueryData(['messages', roomId], (old) =>
        [...(old || []), optimisticUserMessage, optimisticThinkingMessage]
      );

      return { previousMessages };
    },
    onError: (err, newMessage, context) => {
      // 에러 발생 시, 이전 메시지 상태로 롤백
      if (context?.previousMessages) {
        queryClient.setQueryData(['messages',roomId], context.previousMessages);
      }
      showError('메시지 전송에 실패했습니다. 다시 시도해주세요.');
    },
    onSuccess: (data, variables, context) => {
      // 성공 시 '생각 중...' 메시지를 실제 응답으로 교체
      queryClient.setQueryData(['messages', roomId], (old) => {
        // '생각 중...' 메시지를 찾아서 실제 응답으로 교체
        const newMessages = old.filter(msg => !msg.isThinking);
        return [...newMessages, data];
      });
    },
    onSettled: () => {
      // 최종적으로 서버 데이터와 동기화
      queryClient.invalidateQueries({ queryKey: ['messages', roomId] });
    },
  });

  const uploadMutation = useMutation({
    mutationFn: uploadFile,
    onSuccess: () => {
      queryClient.invalidateQueries(['messages', roomId]);
      setIsUploading(false);
    },
    onError: () => {
      setIsUploading(false);
    },
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!message.trim() || !roomId || messageMutation.isLoading || isUploading || disabled) return;
    messageMutation.mutate({ roomId, content: message });
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file && roomId && !disabled) {
      setIsUploading(true);
      uploadMutation.mutate({ roomId, file });
    }
    e.target.value = '';
  };

  return (
    <div className="flex items-center gap-3">
      {/* 파일 업로드 버튼 */}
      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        disabled={disabled}
        className="p-2 text-muted hover:text-text transition-colors duration-150 focus-ring disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <svg viewBox="0 0 16 16" fill="currentColor" className="w-5 h-5">
          <path d="M8 0C3.6 0 0 3.6 0 8s3.6 8 8 8 8-3.6 8-8-3.6-8-8-8zm4 9H7v5H5V9H0V7h5V2h2v5h5v2z"/>
        </svg>
      </button>

      {/* 메시지 입력 필드 */}
      <form onSubmit={handleSubmit} className="flex-1">
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder={disabled ? "룸을 선택해주세요" : "무엇이든 물어보세요..."}
          disabled={disabled || messageMutation.isLoading || isUploading}
          className="w-full px-4 py-3 bg-panel-elev border border-border rounded-input text-body text-text placeholder-muted focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent disabled:opacity-50 disabled:cursor-not-allowed"
        />
      </form>

      {/* 전송 버튼 */}
      <button
        type="submit"
        onClick={handleSubmit}
        disabled={!message.trim() || !roomId || messageMutation.isLoading || isUploading || disabled}
        className="p-3 bg-accent hover:bg-accent-weak text-white rounded-button transition-colors duration-150 focus-ring disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M22 2L11 13M22 2L15 22L11 13M22 2L2 9L11 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>

      {/* 숨겨진 파일 입력 */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileSelect}
        style={{ display: 'none' }}
        accept="image/*,.pdf,.doc,.docx,.txt"
      />
    </div>
  );
};

export default ChatInput;
