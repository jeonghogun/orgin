import React, { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import PropTypes from 'prop-types';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient, { resolveApiUrl } from '../../lib/apiClient';
import { useMessages, useGenerationSettings, setMessages, addMessage, appendStreamChunk, setMessageStatus, markMessageError } from '../../store/useConversationStore';
import useRealtimeChannel from '../../hooks/useRealtimeChannel';
import RoomHeader from '../RoomHeader';
import ChatTimeline from './ChatTimeline';
import Composer from './Composer';
import DiffViewModal from './DiffViewModal';
import toast from 'react-hot-toast';
import { ROOM_TYPES } from '../../constants';

const ROOM_TYPE_LABELS = {
  [ROOM_TYPES.MAIN]: '메인 룸',
  [ROOM_TYPES.SUB]: '세부 룸',
  [ROOM_TYPES.REVIEW]: '검토 룸',
};

const AUTO_RETRY_LIMIT = 1;
const AUTO_RETRY_DELAY_MS = 1200;

const ChatView = ({ threadId, currentRoom }) => {
  const [attachments, setAttachments] = useState([]);
  const [viewingMessageHistory, setViewingMessageHistory] = useState(null);
  const [exportJob, setExportJob] = useState(null);
  const [activeStreamUrl, setActiveStreamUrl] = useState(null);
  const [activeMessageId, setActiveMessageId] = useState(null);
  const autoRetryTimeoutRef = useRef(null);

  const messages = useMessages(threadId);
  const { model, temperature, maxTokens } = useGenerationSettings();
  const queryClient = useQueryClient();

  // --- Data Fetching and Mutations ---

  const { data: fetchedMessages, isLoading, error } = useQuery({
    queryKey: ['messages', threadId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/api/convo/threads/${threadId}/messages`);
      return data;
    },
    enabled: !!threadId,
    retry: 1,
    onError: (queryError) => {
      const detail = queryError?.response?.data?.detail || '대화를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.';
      toast.error(detail);
    },
  });

  useEffect(() => {
    if (fetchedMessages) {
      // Check if the store already has messages to avoid overwriting optimistic updates
      const existingMessages = queryClient.getQueryData(['messages', threadId]);
      if (!existingMessages || existingMessages.length === 0) {
        setMessages(threadId, fetchedMessages.reverse());
      }
    }
  }, [fetchedMessages, threadId, setMessages, queryClient]);

  const uploadFileMutation = useMutation({
    mutationFn: (file) => {
      const formData = new FormData();
      formData.append('file', file);
      return apiClient.post('/api/uploads', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
    },
    onSuccess: (response) => {
      setAttachments((prev) => [...prev, response.data]);
    },
    onError: (error) => {
      const detail = error?.response?.data?.detail || '파일 업로드에 실패했습니다. 다시 시도해주세요.';
      toast.error(detail);
    }
  });

  const sendMessageMutation = useMutation({
    mutationFn: async (newMessage) => {
      if (!threadId) {
        throw new Error('활성화된 스레드가 없어 메시지를 보낼 수 없습니다.');
      }
      const { retryOf, ...payload } = newMessage;
      const { data } = await apiClient.post(`/api/convo/threads/${threadId}/messages`, payload);
      return { messageId: data.messageId, retryOf };
    },
    onSuccess: ({ messageId, retryOf }, variables) => {
      const attachmentsForMeta = Array.isArray(variables.attachments) ? variables.attachments : [];
      const retryPayload = {
        content: variables.content,
        attachments: attachmentsForMeta,
        model: variables.model,
        temperature: variables.temperature,
        max_tokens: variables.max_tokens,
      };

      if (retryOf?.assistantMessageId) {
        setMessageStatus(threadId, retryOf.assistantMessageId, 'archived', {
          retriedAt: Date.now(),
        });
      } else {
        addMessage(threadId, {
          id: `temp_${Date.now()}`,
          role: 'user',
          content: variables.content,
          status: 'complete',
          created_at: Math.floor(Date.now() / 1000),
          meta: { attachments: attachmentsForMeta },
        });
        setAttachments([]);
      }

      addMessage(threadId, {
        id: messageId,
        role: 'assistant',
        content: '',
        status: 'streaming',
        model: variables.model,
        created_at: Math.floor(Date.now() / 1000),
        meta: {
          attachments: attachmentsForMeta,
          retryPayload,
          retryOf: retryOf || null,
        },
      });

      setActiveMessageId(messageId);
      setActiveStreamUrl(`/api/convo/messages/${messageId}/stream`);
    },
    onError: (mutationError, variables) => {
      const detail = mutationError?.response?.data?.detail || '메시지 전송에 실패했어요. 다시 시도해주세요.';
      toast.error(detail);
      if (variables?.retryOf?.assistantMessageId) {
        markMessageError(
          threadId,
          variables.retryOf.assistantMessageId,
          detail,
          '⚠️ 응답을 다시 가져오지 못했어요. 잠시 후 다시 시도해주세요.'
        );
      }
    },
  });

  // --- SSE Handling via custom hook ---

  const streamErrorFallback = '⚠️ 응답 생성이 중단되었어요. 다시 시도해주세요.';

  const handleStreamError = useCallback((error) => {
    console.error('Streaming error received:', error);

    const targetMessage = messages.find((message) => message.id === activeMessageId);
    const nextAttemptCount = (targetMessage?.meta?.retryAttempts ?? 0) + 1;

    if (activeMessageId) {
      markMessageError(threadId, activeMessageId, error.message || streamErrorFallback, streamErrorFallback);
    }

    const displayMessage = error.message || streamErrorFallback;
    toast.error(displayMessage);

    if (autoRetryTimeoutRef.current) {
      clearTimeout(autoRetryTimeoutRef.current);
      autoRetryTimeoutRef.current = null;
    }

    const isManualRetry = Boolean(targetMessage?.meta?.retryOf);

    if (targetMessage?.meta?.retryPayload && !isManualRetry && nextAttemptCount <= AUTO_RETRY_LIMIT) {
      const toastId = `auto-retry-${activeMessageId}`;
      toast.loading('끊어진 응답을 다시 요청하는 중입니다...', { id: toastId });
      autoRetryTimeoutRef.current = setTimeout(() => {
        handleRetry(targetMessage);
        toast.success('응답을 다시 요청했어요.', { id: toastId });
        autoRetryTimeoutRef.current = null;
      }, AUTO_RETRY_DELAY_MS);
    }

    setActiveMessageId(null);
    setActiveStreamUrl(null);
    if (threadId) {
      queryClient.invalidateQueries({ queryKey: ['messages', threadId] });
    }
  }, [activeMessageId, handleRetry, markMessageError, messages, queryClient, streamErrorFallback, threadId]);

  const streamEventHandlers = useMemo(() => ({
    delta: (envelope) => {
      const messageId = envelope?.payload?.message_id || envelope?.meta?.message_id || activeMessageId;
      if (!messageId) return;

      const chunk = envelope?.payload?.delta || envelope?.payload?.content || envelope?.payload?.text;
      if (typeof chunk === 'string' && chunk.trim() !== '') {
        appendStreamChunk(threadId, messageId, chunk);
      }
    },
    meta: (envelope) => {
      const messageId = envelope?.payload?.message_id || envelope?.meta?.message_id || activeMessageId;
      if (!messageId) return;
      if (envelope?.meta) {
        setMessageStatus(threadId, messageId, 'streaming', { stream: envelope.meta });
      }
    },
    done: (envelope) => {
      const messageId = envelope?.payload?.message_id || envelope?.meta?.message_id || activeMessageId;
      if (!messageId) return;

      const status = envelope?.payload?.status || envelope?.meta?.status;
      if (status === 'failed') {
        const errorMessage = envelope?.payload?.error || streamErrorFallback;
        markMessageError(threadId, messageId, errorMessage, streamErrorFallback);
        toast.error(errorMessage);
      } else {
        const metaUpdates = {};
        if (envelope?.meta) {
          metaUpdates.stream = envelope.meta;
        }
        setMessageStatus(threadId, messageId, 'complete', Object.keys(metaUpdates).length ? metaUpdates : undefined);
      }

      setActiveMessageId(null);
      setActiveStreamUrl(null);
      queryClient.invalidateQueries({ queryKey: ['messages', threadId] });
    },
  }), [activeMessageId, appendStreamChunk, markMessageError, queryClient, setMessageStatus, streamErrorFallback, threadId]);

  useRealtimeChannel({ url: activeStreamUrl, events: streamEventHandlers, onError: handleStreamError });

  useEffect(() => {
    return () => {
      if (autoRetryTimeoutRef.current) {
        clearTimeout(autoRetryTimeoutRef.current);
      }
    };
  }, []);

  // --- Other Actions ---

  const handleSendMessage = useCallback((content) => {
    const payload = {
      content,
      attachments: attachments.map((a) => a.id),
      model,
      temperature,
      max_tokens: maxTokens,
    };
    sendMessageMutation.mutate(payload);
  }, [attachments, maxTokens, model, sendMessageMutation, temperature]);

  const handleRetry = useCallback((message) => {
    if (!threadId || !message?.meta?.retryPayload) {
      return;
    }
    const payload = message.meta.retryPayload;
    const attachmentsForRetry = Array.isArray(payload.attachments) ? payload.attachments : [];
    setMessageStatus(threadId, message.id, 'retrying', {
      retriedAt: Date.now(),
    });
    sendMessageMutation.mutate({
      ...payload,
      attachments: attachmentsForRetry,
      retryOf: { assistantMessageId: message.id },
    });
  }, [sendMessageMutation, setMessageStatus, threadId]);

  const createExportJobMutation = useMutation({
    mutationFn: async (format) => {
      if (!threadId) {
        throw new Error('활성화된 스레드가 없어 내보내기를 시작할 수 없습니다.');
      }
      return apiClient.post(`/api/threads/${threadId}/export/jobs`, null, { params: { format } });
    },
    onSuccess: (response) => setExportJob(response.data),
    onError: (mutationError) => {
      const detail = mutationError?.response?.data?.detail || '내보내기 작업을 시작하지 못했습니다.';
      toast.error(detail);
    }
  });

  const { data: exportStatus } = useQuery({
    queryKey: ['exportStatus', exportJob?.jobId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/api/export/jobs/${exportJob.jobId}`);
      return data;
    },
    onSuccess: (data) => {
      if (data.status === 'done' || data.status === 'error') {
        setExportJob(data);
      }
    },
    refetchInterval: (query) => (query.state.data?.status === 'queued' || query.state.data?.status === 'processing') ? 2000 : false,
    enabled: !!exportJob && (exportJob.status === 'queued' || exportJob.status === 'processing'),
  });

  const headerActions = [{ label: 'Export as ZIP', onClick: () => createExportJobMutation.mutate('zip'), variant: 'secondary' }];

  const headerTitle = currentRoom?.name || '대화 스레드';
  const headerSubtitle = useMemo(() => {
    const parts = [];
    if (currentRoom?.type) {
      const typeLabel = ROOM_TYPE_LABELS[currentRoom.type] || '대화 스레드';
      parts.push(typeLabel);
    }
    if (threadId) {
      parts.push(`Thread ID: ${threadId}`);
    }
    return parts.length > 0 ? parts.join(' · ') : undefined;
  }, [currentRoom, threadId]);

  return (
    <div className="flex flex-col h-full bg-white dark:bg-gray-800">
      <RoomHeader title={headerTitle} subtitle={headerSubtitle} actions={headerActions} />

      {exportJob && (
        <div className="p-2 text-center bg-blue-100 dark:bg-blue-900 text-sm text-blue-800 dark:text-blue-200">
          Export status: <strong>{exportStatus?.status || exportJob.status}</strong>.
          {(exportStatus?.status === 'done' || exportJob.status === 'done') && (
            <a
              href={resolveApiUrl(`/api/export/jobs/${exportJob.jobId}/download`)}
              className="font-bold ml-2 underline"
              download
            >
              Download
            </a>
          )}
          {(exportStatus?.status === 'error' || exportJob.status === 'error') && (
            <span className="ml-2 text-red-500">{exportStatus?.error_message || 'An unknown error occurred.'}</span>
          )}
        </div>
      )}

      {viewingMessageHistory && (
        <DiffViewModal messageId={viewingMessageHistory} onClose={() => setViewingMessageHistory(null)} />
      )}
      <div className="flex-1 overflow-y-auto p-4">
        <ChatTimeline
          messages={messages}
          isLoading={isLoading}
          error={error}
          onRetry={handleRetry}
        />
      </div>
      <div className="p-4 border-t border-gray-200 dark:border-gray-700">
        <Composer
          messages={messages}
          onSendMessage={handleSendMessage}
          onFileUpload={uploadFileMutation.mutate}
          isLoading={sendMessageMutation.isPending}
          isUploading={uploadFileMutation.isPending}
        />
      </div>
    </div>
  );
};

ChatView.propTypes = {
  threadId: PropTypes.string,
  currentRoom: PropTypes.shape({
    room_id: PropTypes.string,
    name: PropTypes.string,
    type: PropTypes.string,
    parent_id: PropTypes.string,
  }),
};

export default ChatView;
