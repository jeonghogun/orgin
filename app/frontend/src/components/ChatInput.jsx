import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { SSE } from 'sse.js';
import apiClient, { resolveApiUrl } from '../lib/apiClient';
import { useAppContext } from '../context/AppContext';
import {
  useRoomCreationRequest,
  clearRoomCreation,
  useReviewRoomCreation,
  clearReviewRoomCreation,
  startRoomCreation as activateRoomCreationPrompt,
  startReviewRoomCreation,
  addReviewRoomHistory,
} from '../store/useConversationStore';
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

const formatFileSize = (bytes) => {
  if (!Number.isFinite(bytes)) return '';
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const size = bytes / 1024 ** index;
  return `${size.toFixed(size >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
};

const isImageFile = (file) => {
  if (!file) return false;
  const type = typeof file === 'string' ? file : file.type;
  return typeof type === 'string' && type.startsWith('image/');
};

const streamMessageApi = ({ roomId, content, onChunk, onIdReceived, onMeta }) =>
  new Promise((resolve, reject) => {
    const source = new SSE(resolveApiUrl(`/api/rooms/${roomId}/messages/stream`), {
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

import { useChatInputState } from '../hooks/useChatInputState';
import { ROOM_TYPES } from '../constants';

const ChatInput = ({ roomId, roomData, disabled = false }) => {
  const fileInputRef = useRef(null);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { showError } = useAppContext();
  const [isComposing, setIsComposing] = useState(false);
  const [streamStatus, setStreamStatus] = useState(createInitialStreamStatus());
  const [pendingAttachments, setPendingAttachments] = useState([]);
  const attachmentsRef = useRef([]);
  const [isUploadingAttachments, setIsUploadingAttachments] = useState(false);

  const {
    mode,
    inputValue,
    placeholder,
    handleInputChange,
    resetState,
  } = useChatInputState();

  const roomCreationRequest = useRoomCreationRequest();
  const reviewRoomCreation = useReviewRoomCreation();

  const isRoomCreationActiveForRoom = roomCreationRequest?.active && roomCreationRequest?.parentId === roomId;
  const isReviewRoomCreationActive = reviewRoomCreation?.active && reviewRoomCreation?.parentId === roomId;
  const isLocalCreationMode = mode !== 'default';
  const showCancelButton = isRoomCreationActiveForRoom || isReviewRoomCreationActive || isLocalCreationMode;

  const resetAttachments = useCallback(() => {
    setPendingAttachments((prev) => {
      prev.forEach((attachment) => {
        if (attachment?.previewUrl) {
          URL.revokeObjectURL(attachment.previewUrl);
        }
      });
      return [];
    });
  }, []);

  const handleRemoveAttachment = useCallback((attachmentId) => {
    setPendingAttachments((prev) => {
      const target = prev.find((item) => item.id === attachmentId);
      if (target?.previewUrl) {
        URL.revokeObjectURL(target.previewUrl);
      }
      return prev.filter((item) => item.id !== attachmentId);
    });
  }, []);

  useEffect(() => {
    attachmentsRef.current = pendingAttachments;
  }, [pendingAttachments]);

  useEffect(() => () => {
    attachmentsRef.current.forEach((attachment) => {
      if (attachment?.previewUrl) {
        URL.revokeObjectURL(attachment.previewUrl);
      }
    });
  }, []);

  useEffect(() => {
    resetAttachments();
  }, [roomId, resetAttachments]);

  const removePendingPromptMessage = useCallback(
    (overrideParentId, overrideMessageId) => {
      const targetParentId = overrideParentId ?? roomCreationRequest?.parentId;
      const targetMessageId = overrideMessageId ?? roomCreationRequest?.promptMessageId;

      if (!targetParentId || !targetMessageId) {
        return;
      }

      queryClient.setQueryData(['messages', targetParentId], (old = []) => {
        if (!Array.isArray(old) || old.length === 0) {
          return old;
        }

        const next = old.filter((msg) => msg.message_id !== targetMessageId);
        return next.length === old.length ? old : next;
      });
    },
    [queryClient, roomCreationRequest]
  );

  const handleCancelCreation = useCallback(() => {
    removePendingPromptMessage();
    if (isRoomCreationActiveForRoom) {
      clearRoomCreation();
    }
    if (isReviewRoomCreationActive) {
      clearReviewRoomCreation();
    }
    resetState();
    resetAttachments();
  }, [
    clearReviewRoomCreation,
    clearRoomCreation,
    isReviewRoomCreationActive,
    isRoomCreationActiveForRoom,
    removePendingPromptMessage,
    resetState,
    resetAttachments,
  ]);

  const createRoomMutation = useMutation({
    mutationFn: async ({ name, type, parentId }) => {
      const { data } = await apiClient.post('/api/rooms', { name, type, parent_id: parentId });
      return data;
    },
    onSuccess: (newRoom, variables) => {
      queryClient.invalidateQueries({ queryKey: ['rooms'] });
      removePendingPromptMessage(variables?.parentId, variables?.promptMessageId);
      clearRoomCreation();
      navigate(`/rooms/${newRoom.room_id}`);
    },
    onError: (error) => {
      showError(error?.response?.data?.detail || 'Could not create room.');
    }
  });

  const interactiveReviewRoomMutation = useMutation({
    mutationFn: async ({ parentId, topic, history }) => {
      const { data } = await apiClient.post(`/api/rooms/${parentId}/create-review-room`, { topic, history });
      return data;
    },
    onSuccess: (data, variables) => {
      const { parentId, promptMessageId } = variables || {};
      if (data.status === 'created') {
        queryClient.setQueryData(['rooms'], (oldRooms = []) => {
          if (!Array.isArray(oldRooms)) return oldRooms;
          const exists = oldRooms.some(room => room.room_id === data.room.room_id);
          if (exists) return oldRooms;
          return [...oldRooms, data.room];
        });
        navigate(`/rooms/${data.room.room_id}`);
        removePendingPromptMessage(parentId, promptMessageId);
        clearRoomCreation();
        clearReviewRoomCreation();
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
        if (data.question && reviewRoomCreation?.active && reviewRoomCreation.parentId === parentId) {
          addReviewRoomHistory({ role: 'assistant', content: data.question });
        }
        activateRoomCreationPrompt(
          parentId,
          ROOM_TYPES.REVIEW,
          data.question || messageToInsert.content,
          messageToInsert.message_id,
        );
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

  const handleSubmit = async (e) => {
    e.preventDefault();
    const trimmed = inputValue.trim();
    if ((!trimmed && pendingAttachments.length === 0) || !roomId || streamMutation.isPending || disabled || isUploadingAttachments) {
      return;
    }

    if (pendingAttachments.length > 0 && (roomCreationRequest?.active || mode !== 'default')) {
      showError('현재 단계에서는 파일을 전송할 수 없습니다. 일반 메시지 모드에서 다시 시도해주세요.');
      return;
    }

    const baseContent = trimmed ? inputValue : '';

    const submitInteractiveReview = (parentId, promptText, promptMessageId) => {
      const isActive = reviewRoomCreation?.active && reviewRoomCreation.parentId === parentId;
      const baseHistory = isActive ? [...(reviewRoomCreation.history || [])] : [];
      const assistantEntry = promptText ? { role: 'assistant', content: promptText } : null;

      let shouldAppendAssistant = Boolean(assistantEntry);
      if (shouldAppendAssistant && baseHistory.length > 0) {
        const lastEntry = baseHistory[baseHistory.length - 1];
        if (lastEntry?.role === 'assistant' && lastEntry?.content === assistantEntry.content) {
          shouldAppendAssistant = false;
        }
      }

      const userEntry = { role: 'user', content: trimmed };
      const historyPayload = [...baseHistory];
      if (assistantEntry && shouldAppendAssistant) {
        historyPayload.push(assistantEntry);
      }
      historyPayload.push(userEntry);

      if (isActive) {
        if (assistantEntry && shouldAppendAssistant) {
          addReviewRoomHistory(assistantEntry);
        }
        addReviewRoomHistory(userEntry);
      } else {
        startReviewRoomCreation(parentId, trimmed, historyPayload);
      }

      interactiveReviewRoomMutation.mutate({
        parentId,
        topic: trimmed,
        history: historyPayload,
        promptMessageId,
      });

      resetState();
    };

    // Global room-creation flow triggered from the sidebar
    if (roomCreationRequest?.active && roomCreationRequest.parentId === roomId) {
      if (roomCreationRequest.type === ROOM_TYPES.SUB) {
        createRoomMutation.mutate({
          name: trimmed,
          type: ROOM_TYPES.SUB,
          parentId: roomCreationRequest.parentId,
          promptMessageId: roomCreationRequest.promptMessageId,
        });
        resetState();
      } else if (roomCreationRequest.type === ROOM_TYPES.REVIEW) {
        submitInteractiveReview(
          roomCreationRequest.parentId,
          roomCreationRequest.promptText,
          roomCreationRequest.promptMessageId,
        );
      }
      return;
    }

    switch (mode) {
      case 'creating_sub_room':
        createRoomMutation.mutate({ name: trimmed, type: 'sub', parentId: roomId });
        resetState();
        break;
      case 'creating_review':
        submitInteractiveReview(roomId, null);
        break;
      default:
        let attachmentSegments = [];
        if (pendingAttachments.length > 0) {
          const attachmentsSnapshot = [...pendingAttachments];
          setIsUploadingAttachments(true);
          try {
            const uploadedContents = [];
            for (const attachment of attachmentsSnapshot) {
              const formData = new FormData();
              formData.append('file', attachment.file);
              formData.append('attach_only', 'true');
              const response = await apiClient.post(`/api/rooms/${roomId}/upload`, formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
              });
              if (response?.data?.content) {
                uploadedContents.push(response.data.content);
              }
            }
            attachmentSegments = uploadedContents;
            resetAttachments();
          } catch (error) {
            console.error('Failed to upload attachment', error);
            showError(error?.response?.data?.detail || '파일 업로드에 실패했습니다.');
            setIsUploadingAttachments(false);
            return;
          } finally {
            setIsUploadingAttachments(false);
          }
        }

        const composedSegments = [];
        if (baseContent) {
          composedSegments.push(baseContent);
        }
        if (attachmentSegments.length > 0) {
          composedSegments.push(attachmentSegments.join('\n\n'));
        }
        const finalContent = composedSegments.join('\n\n');
        const messageTimestamp = Math.floor(Date.now() / 1000);

        // Optimistic updates for streaming chat
        const tempUserId = `temp-user-${Date.now()}`;
        const tempAssistantId = `temp-assistant-${Date.now()}`;
        queryClient.setQueryData(['messages', roomId], (old) => [
          ...(old || []),
          { message_id: tempUserId, role: 'user', content: finalContent || baseContent, timestamp: messageTimestamp },
        ]);
        queryClient.setQueryData(['messages', roomId], (old) => [
          ...(old || []),
          { message_id: tempAssistantId, role: 'assistant', content: '', timestamp: messageTimestamp, isStreaming: true },
        ]);

        setStreamStatus({ ...createInitialStreamStatus(), active: true, lastUpdated: Date.now() });

        streamMutation.mutate({
          roomId,
          content: finalContent || baseContent,
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

  const handleFileSelect = (event) => {
    const files = Array.from(event.target.files || []);
    event.target.value = '';

    if (!files.length || !roomId || disabled || streamMutation.isPending || isUploadingAttachments) {
      return;
    }

    if (roomCreationRequest?.active || mode !== 'default') {
      showError('파일은 일반 채팅에서만 첨부할 수 있습니다.');
      return;
    }

    const nextAttachments = files.map((file) => ({
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      file,
      name: file.name,
      size: file.size,
      type: file.type,
      previewUrl: isImageFile(file) ? URL.createObjectURL(file) : null,
    }));

    setPendingAttachments((prev) => [...prev, ...nextAttachments]);
  };

  return (
    <div className="space-y-2">
      <StreamingStatusIndicator status={streamStatus} />
      <div className="flex items-start gap-3">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || isUploadingAttachments || streamMutation.isPending}
          className="flex items-center justify-center h-12 w-12 text-muted transition-colors duration-150 hover:text-text focus-ring disabled:cursor-not-allowed disabled:opacity-50"
          title="파일 업로드"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
            <line x1="12" y1="5" x2="12" y2="19"></line>
            <line x1="5" y1="12" x2="19" y2="12"></line>
          </svg>
        </button>

        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileSelect}
          className="hidden"
          multiple
          accept="image/*,.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.csv,.txt,.md,.zip"
        />

        <form onSubmit={handleSubmit} className="flex-1 space-y-2">
          {pendingAttachments.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {pendingAttachments.map((attachment) => (
                <div
                  key={attachment.id}
                  className="relative flex w-full max-w-xs items-start gap-3 rounded-lg border border-border bg-panel p-3 pr-9 text-left sm:max-w-[220px]"
                >
                  {attachment.previewUrl ? (
                    <img
                      src={attachment.previewUrl}
                      alt={`${attachment.name} 미리보기`}
                      className="h-12 w-12 rounded-md object-cover"
                    />
                  ) : (
                    <div className="flex h-12 w-12 items-center justify-center rounded-md bg-panel-muted text-muted">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    </div>
                  )}
                  <div className="min-w-0 space-y-1">
                    <div className="truncate text-sm font-medium text-text" title={attachment.name}>
                      {attachment.name}
                    </div>
                    <div className="text-xs text-muted">
                      {formatFileSize(attachment.size)} · {attachment.type || '파일'}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRemoveAttachment(attachment.id)}
                    className="absolute right-2 top-2 text-muted transition-colors duration-150 hover:text-text focus-ring"
                  >
                    <span className="sr-only">첨부 삭제</span>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="relative">
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
              disabled={disabled || streamMutation.isPending || isUploadingAttachments}
              className="w-full resize-none rounded-lg border border-border bg-panel-elevated px-4 py-3 pr-12 text-gray-900 placeholder-muted focus:outline-none focus:ring-2 focus:ring-accent/50 disabled:cursor-not-allowed disabled:opacity-50"
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
              disabled={(
                !inputValue.trim() && pendingAttachments.length === 0
              ) || !roomId || streamMutation.isPending || disabled || isUploadingAttachments}
              className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md bg-accent p-2 text-white transition-colors duration-150 hover:bg-accent-hover focus-ring disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isUploadingAttachments ? (
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" opacity="0.25" />
                  <path d="M22 12a10 10 0 0 1-10 10" />
                </svg>
              ) : (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 2L11 13M22 2L15 22L11 13M22 2L2 9L11 13"/></svg>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default ChatInput;
