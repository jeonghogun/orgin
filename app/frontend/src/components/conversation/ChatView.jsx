import React, { useEffect, useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { useMessages, useConversationActions, useGenerationSettings } from '../../store/useConversationStore';
import useEventSource from '../../hooks/useEventSource';
import RoomHeader from '../RoomHeader';
import ChatTimeline from './ChatTimeline';
import Composer from './Composer';
import DiffViewModal from './DiffViewModal';

const ChatView = ({ threadId }) => {
  const [attachments, setAttachments] = useState([]);
  const [viewingMessageHistory, setViewingMessageHistory] = useState(null);
  const [exportJob, setExportJob] = useState(null);
  const [activeStreamUrl, setActiveStreamUrl] = useState(null);

  const messages = useMessages(threadId);
  const { setMessages, addMessage, appendStreamChunk } = useConversationActions();
  const { model, temperature, maxTokens } = useGenerationSettings();
  const queryClient = useQueryClient();

  // --- Data Fetching and Mutations ---

  const { isLoading, error } = useQuery({
    queryKey: ['messages', threadId],
    queryFn: async () => {
      const { data } = await axios.get(`/api/convo/threads/${threadId}/messages`);
      return data;
    },
    onSuccess: (data) => {
      setMessages(threadId, data.reverse());
    },
    enabled: !!threadId,
  });

  const uploadFileMutation = useMutation({
    mutationFn: (file) => {
      const formData = new FormData();
      formData.append('file', file);
      return axios.post('/api/uploads', formData);
    },
    onSuccess: (response) => {
      setAttachments((prev) => [...prev, response.data]);
    },
  });

  const sendMessageMutation = useMutation({
    mutationFn: (newMessage) => axios.post(`/api/convo/threads/${threadId}/messages`, newMessage),
    onSuccess: (response, variables) => {
      const { messageId } = response.data;
      addMessage(threadId, {
        id: `temp_${Date.now()}`,
        role: 'user',
        content: variables.content,
        status: 'complete',
        created_at: Math.floor(Date.now() / 1000),
        meta: { attachments: variables.attachments }
      });
      addMessage(threadId, { id: messageId, role: 'assistant', content: '', status: 'draft', model: variables.model, created_at: Math.floor(Date.now() / 1000) });
      setAttachments([]);
      setActiveStreamUrl(`/api/convo/messages/${messageId}/stream`);
    },
  });

  // --- SSE Handling via custom hook ---

  const streamEventHandlers = useMemo(() => ({
    delta: (e) => {
      if (!e.data || e.data.trim() === '') return;
      const messageId = activeStreamUrl?.split('/')[4];
      if (!messageId) return;

      let content;
      try {
        // Try to parse as JSON first
        const data = JSON.parse(e.data);
        // Extract content from a potential JSON structure
        content = data.content || data.text || '';
      } catch (error) {
        // If parsing fails, assume it's a plain text chunk
        content = e.data;
      }

      if (content) {
        appendStreamChunk(threadId, messageId, content);
      }
    },
    done: (e) => {
      setActiveStreamUrl(null); // Stop the connection
      queryClient.invalidateQueries({ queryKey: ['messages', threadId] });
    },
    error: (e) => {
      // It's better to show an error to the user.
      // For now, just log it and stop the stream.
      console.error("Streaming error received:", e);
      setActiveStreamUrl(null); // Stop trying to reconnect on fatal error
    }
  }), [threadId, activeStreamUrl, appendStreamChunk, queryClient]);

  useEventSource(activeStreamUrl, streamEventHandlers);

  // --- Other Actions ---

  const handleSendMessage = (content) => {
    sendMessageMutation.mutate({
      content,
      attachments: attachments.map(a => a.id),
      model,
      temperature,
      max_tokens: maxTokens,
    });
  };

  const createExportJobMutation = useMutation({
    mutationFn: (format) => axios.post(`/api/threads/${threadId}/export/jobs`, null, { params: { format } }),
    onSuccess: (response) => setExportJob(response.data),
    onError: (error) => {
      // Maybe show an error to the user in the future.
    }
  });

  const { data: exportStatus } = useQuery({
    queryKey: ['exportStatus', exportJob?.jobId],
    queryFn: async () => {
      const { data } = await axios.get(`/api/export/jobs/${exportJob.jobId}`);
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

  return (
    <div className="flex flex-col h-full bg-white dark:bg-gray-800">
      <RoomHeader title={`Thread`} subtitle={threadId} actions={headerActions} />

      {exportJob && (
        <div className="p-2 text-center bg-blue-100 dark:bg-blue-900 text-sm text-blue-800 dark:text-blue-200">
          Export status: <strong>{exportStatus?.status || exportJob.status}</strong>.
          {(exportStatus?.status === 'done' || exportJob.status === 'done') && (
            <a href={`/api/export/jobs/${exportJob.jobId}/download`} className="font-bold ml-2 underline" download>Download</a>
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
        <ChatTimeline messages={messages} isLoading={isLoading} error={error} onViewHistory={setViewingMessageHistory} />
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

export default ChatView;
