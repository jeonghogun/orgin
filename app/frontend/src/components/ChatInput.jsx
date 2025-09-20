import React, { useState, useRef, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { SSE } from 'sse.js';
import { useAppContext } from '../context/AppContext';
import { useRoomCreationRequest, clearRoomCreation, useReviewRoomCreation, clearReviewRoomCreation } from '../store/useConversationStore';
import { parseRealtimeEvent, withFallbackMeta } from '../utils/realtime';

// Use fetch for true streaming response
const createInitialStreamStatus = () => ({
  active: false,
  chunkCount: 0,
  model: null,
  provider: null,
  lastUpdated: null,
});

const StreamingStatusIndicator = ({ status }) => {
  if (!status?.active) {
    return null;
  }

  const providerLabel = status.provider ? status.provider.toUpperCase() : null;
  const modelLabel = status.model || null;
  const chunkLabel = status.chunkCount ? `청크 ${status.chunkCount}` : null;

  return (
    <div className="flex items-center justify-between rounded-card border border-accent/50 bg-accent/10 px-3 py-2 text-[11px] font-medium text-accent">
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 animate-pulse rounded-full bg-accent"></span>
        <span>응답 생성 중...</span>
      </div>
      <div className="flex items-center gap-3 uppercase tracking-wide">
        {providerLabel && <span>{providerLabel}</span>}
        {modelLabel && <span>{modelLabel}</span>}
        {chunkLabel && <span>{chunkLabel}</span>}
      </div>
    </div>
  );
};

const streamMessageApi = ({ roomId, content, onChunk, onIdReceived, onMeta }) =>
  new Promise((resolve, reject) => {
    const source = new SSE(`/api/rooms/${roomId}/messages/stream`, {
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
      payload: JSON.stringify({ content }),
    });

    let settled = false;

    const cleanup = () => {
      if (!settled) {
        settled = true;
        source.close();
      }
    };

    source.addEventListener('meta', (event) => {
      const envelope = parseRealtimeEvent(event);
      if (!envelope) return;
      const normalized = withFallbackMeta(envelope);
      const payload = { ...(normalized.payload || {}) };
      if (normalized.meta?.chunk_index !== undefined && payload.chunk_index === undefined) {
        payload.chunk_index = normalized.meta.chunk_index;
      }
      if (normalized.meta?.chunk_count !== undefined && payload.chunk_count === undefined) {
        payload.chunk_count = normalized.meta.chunk_count;
      }
      if (normalized.meta?.status && !payload.status) {
        payload.status = normalized.meta.status;
      }
      onMeta?.(payload);
    });

    source.addEventListener('delta', (event) => {
      const envelope = parseRealtimeEvent(event);
      const chunk = envelope?.payload?.delta || envelope?.payload?.content || envelope?.payload?.text;
      if (typeof chunk === 'string') {
        onChunk(chunk);
      }
    });

    source.addEventListener('done', (event) => {
      const envelope = parseRealtimeEvent(event) || {};
      const normalized = withFallbackMeta(envelope);
      const payload = normalized.payload || {};
      if (payload.meta) {
        onMeta?.(payload.meta);
      }
      if (payload.message_id) {
        onIdReceived(payload.message_id);
      }
      cleanup();
      resolve(payload);
    });

    source.addEventListener('error', (event) => {
      const envelope = parseRealtimeEvent(event);
      const message = envelope?.payload?.error || '실시간 응답을 가져오는 중 문제가 발생했습니다.';
      cleanup();
      reject(new Error(message));
    });

    source.onerror = (error) => {
      if (!settled) {
        cleanup();
        reject(error instanceof Error ? error : new Error('네트워크 연결이 끊어졌습니다.'));
      }
    };

    source.stream();
  });

const uploadFileApi = async ({ roomId, file }) => {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await axios.post(`/api/rooms/${roomId}/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
};

import { useChatInputState } from '../hooks/useChatInputState';
import { ROOM_TYPES } from '../constants';

const ChatInput = ({ roomId, roomData, disabled = false }) => {
  const fileInputRef = useRef(null);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { showError } = useAppContext();
  const [isComposing, setIsComposing] = useState(false);
  const [streamStatus, setStreamStatus] = useState(createInitialStreamStatus());

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

  const isRoomCreationActiveForRoom = roomCreationRequest?.active && roomCreationRequest?.parentId === roomId;
  const isReviewRoomCreationActive = reviewRoomCreation?.active && reviewRoomCreation?.parentId === roomId;
  const isLocalCreationMode = mode !== 'default';
  const showCancelButton = isRoomCreationActiveForRoom || isReviewRoomCreationActive || isLocalCreationMode;

  const removePendingPromptMessage = useCallback(() => {
    if (isRoomCreationActiveForRoom && roomCreationRequest?.promptMessageId) {
      queryClient.setQueryData(['messages', roomCreationRequest.parentId], (old = []) => {
        if (!Array.isArray(old)) {
          return old;
        }
        return old.filter((msg) => msg.message_id !== roomCreationRequest.promptMessageId);
      });
    }
  }, [isRoomCreationActiveForRoom, queryClient, roomCreationRequest]);

  const handleCancelCreation = useCallback(() => {
    removePendingPromptMessage();
    if (isRoomCreationActiveForRoom) {
      clearRoomCreation();
    }
    if (isReviewRoomCreationActive) {
      clearReviewRoomCreation();
    }
    resetState();
  }, [
    clearReviewRoomCreation,
    clearRoomCreation,
    isReviewRoomCreationActive,
    isRoomCreationActiveForRoom,
    removePendingPromptMessage,
    resetState,
  ]);

  const createRoomMutation = useMutation({
    mutationFn: async ({ name, type, parentId }) => {
      const { data } = await axios.post('/api/rooms', { name, type, parent_id: parentId });
      return data;
    },
    onSuccess: (newRoom) => {
      queryClient.invalidateQueries({ queryKey: ['rooms'] });
      navigate(`/rooms/${newRoom.room_id}`);
    },
    onError: (error) => {
      showError(error?.response?.data?.detail || 'Could not create room.');
    }
  });

  const interactiveReviewRoomMutation = useMutation({
    mutationFn: async ({ parentId, topic, history }) => {
      const { data } = await axios.post(`/api/rooms/${parentId}/create-review-room`, { topic, history });
      return data;
    },
    onSuccess: (data, { parentId }) => {
      if (data.status === 'created') {
        queryClient.setQueryData(['rooms'], (oldRooms = []) => {
          if (!Array.isArray(oldRooms)) return oldRooms;
          const exists = oldRooms.some(room => room.room_id === data.room.room_id);
          if (exists) return oldRooms;
          return [...oldRooms, data.room];
        });
        navigate(`/rooms/${data.room.room_id}`);
      } else if (data.status === 'needs_more_context') {
        const persistedMessage = data.prompt_message;
        const fallbackMessage = {
          message_id: `ai_prompt_${Date.now()}`,
          room_id: parentId,
          role: 'assistant',
          user_id: 'review_assistant',
          content: data.question,
          timestamp: Math.floor(Date.now() / 1000),
        };
        const messageToInsert = persistedMessage || fallbackMessage;
        queryClient.setQueryData(['messages', parentId], (old = []) => {
          if (!Array.isArray(old)) {
            return [messageToInsert];
          }
          if (old.some((msg) => msg.message_id === messageToInsert.message_id)) {
            return old;
          }
          return [...old, messageToInsert];
        });
      }
    },
    onError: (error) => {
      showError(error?.response?.data?.detail || 'Could not create review room.');
    },
  });

  const streamMutation = useMutation({
    mutationFn: streamMessageApi,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['messages', roomId] });
      resetState();
      setStreamStatus(createInitialStreamStatus());
    },
    onError: (err) => {
      showError(err.message);
      queryClient.invalidateQueries({ queryKey: ['messages', roomId] });
      resetState();
      setStreamStatus(createInitialStreamStatus());
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

    // Global room-creation flow triggered from the sidebar
    if (roomCreationRequest?.active && roomCreationRequest.parentId === roomId) {
      const trimmed = inputValue.trim();
      if (!trimmed) return;

      if (roomCreationRequest.type === ROOM_TYPES.SUB) {
        createRoomMutation.mutate({
          name: trimmed,
          type: ROOM_TYPES.SUB,
          parentId: roomCreationRequest.parentId,
        });
      } else if (roomCreationRequest.type === ROOM_TYPES.REVIEW) {
        interactiveReviewRoomMutation.mutate({
          parentId: roomCreationRequest.parentId,
          topic: trimmed,
          history: [
            { role: 'assistant', content: roomCreationRequest.promptText },
            { role: 'user', content: trimmed },
          ],
        });
      }

      clearRoomCreation();
      resetState();
      return;
    }

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

        setStreamStatus({ ...createInitialStreamStatus(), active: true, lastUpdated: Date.now() });

        streamMutation.mutate({
          roomId,
          content: inputValue,
          onChunk: (chunk) => queryClient.setQueryData(['messages', roomId], (old) => old.map((m) => m.message_id === tempAssistantId ? { ...m, content: m.content + chunk } : m)),
          onIdReceived: (finalId) => queryClient.setQueryData(['messages', roomId], (old) => old.map((m) => m.message_id === tempAssistantId ? { ...m, message_id: finalId, isStreaming: false } : m)),
          onMeta: (meta) => {
            setStreamStatus((prev) => {
              const next = { ...prev };
              if (meta.status === 'started') {
                next.active = true;
              }
              if (meta.status === 'completed' || meta.status === 'failed') {
                next.active = false;
              }
              if (typeof meta.chunk_index === 'number') {
                next.chunkCount = meta.chunk_index;
                next.active = true;
              }
              if (typeof meta.chunk_count === 'number') {
                next.chunkCount = meta.chunk_count;
              }
              if (meta.model) {
                next.model = meta.model;
              }
              if (meta.provider) {
                next.provider = meta.provider;
              }
              next.lastUpdated = Date.now();
              return next;
            });
          }
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
    <div className="space-y-2">
      <StreamingStatusIndicator status={streamStatus} />
      <div className="flex items-center gap-3">
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
            if (isComposing) {
              return;
            }
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
          onCompositionStart={() => setIsComposing(true)}
          onCompositionEnd={() => setIsComposing(false)}
          placeholder={(() => {
            if (disabled) return "룸을 선택해주세요";
            if (isRoomCreationActiveForRoom) return roomCreationRequest?.promptText || '';
            if (isReviewRoomCreationActive) return "어떤 주제로 검토룸을 열까요?";
            return "무엇이든 물어보세요...";
          })()}
          disabled={disabled || streamMutation.isPending || uploadMutation.isPending}
          className="w-full px-4 py-3 pr-12 bg-panel-elevated border border-border rounded-lg text-text placeholder-muted focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent disabled:opacity-50 disabled:cursor-not-allowed resize-none"
          rows={1}
        />
        {showCancelButton && (
          <button
            type="button"
            onClick={handleCancelCreation}
            className="absolute right-12 top-1/2 -translate-y-1/2 rounded-md px-2 py-1 text-xs font-medium text-muted hover:text-text focus-ring"
          >
            취소
          </button>
        )}
        <button
          type="submit"
          disabled={!inputValue.trim() || !roomId || streamMutation.isPending || uploadMutation.isPending || disabled}
          className="absolute right-3 top-1/2 -translate-y-1/2 p-2 bg-accent hover:bg-accent-hover text-white rounded-md transition-colors duration-150 focus-ring disabled:opacity-50 disabled:cursor-not-allowed"
        >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 2L11 13M22 2L15 22L11 13M22 2L2 9L11 13"/></svg>
        </button>
      </form>
    </div>
    </div>
  );
};

export default ChatInput;
