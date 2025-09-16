import React, { useState, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { SSE } from 'sse.js';
import { useAppContext } from '../context/AppContext';
import { useRoomCreationRequest, clearRoomCreation, useReviewRoomCreation, addReviewRoomHistory, clearReviewRoomCreation } from '../store/useConversationStore';

// Use fetch for true streaming response
const streamMessageApi = async ({ roomId, content, onChunk, onIdReceived }) => {
  const response = await fetch(`/api/rooms/${roomId}/messages/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || 'Failed to start stream');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop(); // Keep the last, potentially incomplete line

    for (const line of lines) {
      if (line.trim() === '') continue;
      try {
        const parsed = JSON.parse(line);
        if (parsed.delta) {
          onChunk(parsed.delta);
        }
        if (parsed.done) {
          onIdReceived(parsed.message_id);
          return; // Stream is finished
        }
      } catch (e) {
        console.error('Failed to parse stream chunk:', line, e);
      }
    }
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

import { useChatInputState } from '../hooks/useChatInputState';

const ChatInput = ({ roomId, roomData, disabled = false, createRoomMutation, interactiveReviewRoomMutation }) => {
  const fileInputRef = useRef(null);
  const queryClient = useQueryClient();
  const { showError } = useAppContext();
  
  const {
    mode,
    inputValue,
    placeholder,
    startSubRoomCreation,
    startReviewCreation,
    handleInputChange,
    resetState,
  } = useChatInputState();

  const roomCreationRequest = useRoomCreationRequest();
  const reviewRoomCreation = useReviewRoomCreation();

  const streamMutation = useMutation({
    mutationFn: streamMessageApi,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['messages', roomId] });
      resetState();
    },
    onError: (err) => {
      showError(err.message);
      queryClient.invalidateQueries({ queryKey: ['messages', roomId] });
      resetState();
    },
  });

  const uploadMutation = useMutation({
    mutationFn: uploadFileApi,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['messages', roomId] }),
    onError: (err) => showError(err.response?.data?.detail || '파일 업로드에 실패했습니다.'),
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!inputValue.trim() || !roomId || streamMutation.isPending || disabled) return;

    switch (mode) {
      case 'creating_sub_room':
        createRoomMutation.mutate({ name: inputValue.trim(), type: 'sub', parentId: roomId });
        resetState();
        break;
      case 'creating_review':
        interactiveReviewRoomMutation.mutate({ parentId: roomId, topic: inputValue.trim(), history: [] });
        resetState();
        break;
      default:
        // Optimistic updates for streaming chat
        const tempUserId = `temp-user-${Date.now()}`;
        const tempAssistantId = `temp-assistant-${Date.now()}`;
        queryClient.setQueryData(['messages', roomId], (old) => [...(old || []), { message_id: tempUserId, role: 'user', content: inputValue, timestamp: Math.floor(Date.now() / 1000) }]);
        queryClient.setQueryData(['messages', roomId], (old) => [...(old || []), { message_id: tempAssistantId, role: 'assistant', content: '', timestamp: Math.floor(Date.now() / 1000), isStreaming: true }]);

        streamMutation.mutate({
          roomId,
          content: inputValue,
          onChunk: (chunk) => queryClient.setQueryData(['messages', roomId], (old) => old.map((m) => m.message_id === tempAssistantId ? { ...m, content: m.content + chunk } : m)),
          onIdReceived: (finalId) => queryClient.setQueryData(['messages', roomId], (old) => old.map((m) => m.message_id === tempAssistantId ? { ...m, message_id: finalId, isStreaming: false } : m)),
        });
        break;
    }
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
              startSubRoomCreation(roomId);
            } else if (roomData.type === 'sub') {
              startReviewCreation(roomId);
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
          value={inputValue}
          onChange={handleInputChange}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
          placeholder={(() => {
            const isSubRoomCreationActive = roomCreationRequest?.active && roomCreationRequest?.parentId === roomId;
            const isReviewRoomCreationActive = reviewRoomCreation?.active && reviewRoomCreation?.parentId === roomId;

            if (disabled) return "룸을 선택해주세요";
            if (isSubRoomCreationActive) return roomCreationRequest.promptText;
            if (isReviewRoomCreationActive) return "어떤 주제로 검토룸을 열까요?";
            return "무엇이든 물어보세요...";
          })()}
          disabled={disabled || streamMutation.isPending || uploadMutation.isPending}
          className="w-full px-4 py-3 pr-12 bg-panel-elevated border border-border rounded-lg text-text placeholder-muted focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent disabled:opacity-50 disabled:cursor-not-allowed resize-none"
          rows={1}
        />
        <button
          type="submit"
          disabled={!inputValue.trim() || !roomId || streamMutation.isPending || uploadMutation.isPending || disabled}
          className="absolute right-3 top-1/2 -translate-y-1/2 p-2 bg-accent hover:bg-accent-hover text-white rounded-md transition-colors duration-150 focus-ring disabled:opacity-50 disabled:cursor-not-allowed"
        >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 2L11 13M22 2L15 22L11 13M22 2L2 9L11 13"/></svg>
        </button>
      </form>
    </div>
  );
};

export default ChatInput;
