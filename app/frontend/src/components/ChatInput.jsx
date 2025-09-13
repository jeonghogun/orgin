import React, { useState, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { SSE } from 'sse.js';
import { useAppContext } from '../context/AppContext';
import { useRoomCreationRequest, clearRoomCreation } from '../store/useConversationStore';

// Use stream endpoint with proper JSON response handling
const streamMessageApi = async ({ roomId, content, onChunk, onIdReceived }) => {
  try {
    const response = await axios.post(`/api/rooms/${roomId}/messages/stream`, { content });
    const data = response.data;
    
    if (data.success && data.data) {
      // Handle the AI response
      const aiResponse = data.data.ai_response;
      if (aiResponse && aiResponse.content) {
        // Send the full content as a single chunk
        onChunk(aiResponse.content);
        onIdReceived(aiResponse.message_id);
      }
    }
  } catch (error) {
    throw new Error('메시지 전송 중 오류가 발생했습니다: ' + (error.response?.data?.detail || error.message));
  }
};

const uploadFileApi = async ({ roomId, file }) => {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await axios.post(`/api/rooms/${roomId}/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
};

const ChatInput = ({ roomId, roomData, disabled = false, onCreateSubRoom, onCreateReviewRoom, createRoomMutation }) => {
  const [message, setMessage] = useState('');
  const fileInputRef = useRef(null);
  const queryClient = useQueryClient();
  const { showError } = useAppContext();
  const roomCreationRequest = useRoomCreationRequest();
  
  // 디버그용 로그
  console.log('ChatInput - roomCreationRequest:', roomCreationRequest);
  console.log('ChatInput - roomId:', roomId);

  const streamMutation = useMutation({
    mutationFn: streamMessageApi,
    onSuccess: () => {
      // Final invalidation to fetch the true state from the server
      queryClient.invalidateQueries({ queryKey: ['messages', roomId] });
    },
    onError: (err) => {
      showError(err.message);
      // Invalidate to roll back any optimistic updates that weren't handled manually
      queryClient.invalidateQueries({ queryKey: ['messages', roomId] });
    },
  });

  const uploadMutation = useMutation({
    mutationFn: uploadFileApi,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['messages', roomId] });
    },
    onError: (err) => {
      showError(err.response?.data?.detail || '파일 업로드에 실패했습니다.');
    },
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!message.trim() || !roomId || streamMutation.isPending || disabled) return;

    // 룸 생성 요청이 활성화되어 있는지 확인
    if (roomCreationRequest?.active && roomCreationRequest?.parentId === roomId) {
      // 룸 생성 로직
      if (createRoomMutation) {
        createRoomMutation.mutate({
          name: message.trim(),
          type: roomCreationRequest.type,
          parentId: roomId
        });
      }
      clearRoomCreation();
      setMessage('');
      return;
    }

    // 일반 메시지 전송
    streamMutation.mutate({
      roomId,
      content: message,
      onChunk: () => {}, // No-op since we're not streaming
      onIdReceived: () => {}, // No-op since we're not streaming
    });

    setMessage('');
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file && roomId && !disabled) {
      uploadMutation.mutate({ roomId, file });
    }
    e.target.value = '';
  };

  return (
    <div className="flex items-center gap-3 p-4 border-t border-border">
      {/* 파일 업로드 버튼 */}
      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        disabled={disabled || uploadMutation.isPending || streamMutation.isPending}
        className="p-2 text-muted hover:text-text transition-colors duration-150 focus-ring disabled:opacity-50 disabled:cursor-not-allowed"
        title="파일 업로드"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14m-7-7h14"/></svg>
      </button>
      
      {/* + 버튼 - 메인룸과 세부룸에만 표시 */}
      {roomData && (roomData.type === 'main' || roomData.type === 'sub') && (
        <button
          type="button"
          onClick={() => {
            if (roomData.type === 'main') {
              onCreateSubRoom?.(roomId);
            } else if (roomData.type === 'sub') {
              onCreateReviewRoom?.(roomId);
            }
          }}
          disabled={disabled || uploadMutation.isPending || streamMutation.isPending}
          className="p-2 text-muted hover:text-text transition-colors duration-150 focus-ring disabled:opacity-50 disabled:cursor-not-allowed"
          title={roomData.type === 'main' ? "세부룸 추가" : "검토룸 추가"}
        >
          <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 0C3.6 0 0 3.6 0 8s3.6 8 8 8 8-3.6 8-8-3.6-8-8-8zm4 9H7v5H5V9H0V7h5V2h2v5h5v2z"/>
          </svg>
        </button>
      )}
      
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileSelect}
        className="hidden"
        accept="image/*,.pdf,.doc,.docx,.txt"
      />

      <form onSubmit={handleSubmit} className="flex-1 relative">
        <textarea
          key={`textarea-${roomId}-${roomCreationRequest?.active ? 'active' : 'inactive'}`}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
          placeholder={(() => {
            const isRoomCreationActive = roomCreationRequest?.active && roomCreationRequest?.parentId === roomId;
            console.log('Placeholder condition check:', {
              disabled,
              roomCreationRequestActive: roomCreationRequest?.active,
              parentIdMatch: roomCreationRequest?.parentId === roomId,
              isRoomCreationActive,
              promptText: roomCreationRequest?.promptText
            });
            
            if (disabled) return "룸을 선택해주세요";
            if (isRoomCreationActive) return roomCreationRequest.promptText;
            return "무엇이든 물어보세요...";
          })()}
          disabled={disabled || streamMutation.isPending || uploadMutation.isPending}
          className="w-full px-4 py-3 pr-12 bg-panel-elevated border border-border rounded-lg text-text placeholder-muted focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent disabled:opacity-50 disabled:cursor-not-allowed resize-none"
          rows={1}
        />
        <button
          type="submit"
          disabled={!message.trim() || !roomId || streamMutation.isPending || uploadMutation.isPending || disabled}
          className="absolute right-3 top-1/2 -translate-y-1/2 p-2 bg-accent hover:bg-accent-hover text-white rounded-md transition-colors duration-150 focus-ring disabled:opacity-50 disabled:cursor-not-allowed"
        >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 2L11 13M22 2L15 22L11 13M22 2L2 9L11 13"/></svg>
        </button>
      </form>
    </div>
  );
};

export default ChatInput;
