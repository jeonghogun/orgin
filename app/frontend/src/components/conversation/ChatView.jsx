import React, { useEffect, useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { useMessages, useConversationActions, useGenerationSettings } from '../../store/useConversationStore';
import ChatTimeline from './ChatTimeline';
import Composer from './Composer';
import DiffViewModal from './DiffViewModal';

const ChatView = ({ threadId }) => {
  const [attachments, setAttachments] = useState([]);
  const [viewingMessageHistory, setViewingMessageHistory] = useState(null);
  const messages = useMessages(threadId);
  const { setMessages, addMessage, appendStreamChunk, updateMessage } = useConversationActions();
  const { model, temperature, maxTokens } = useGenerationSettings();
  const queryClient = useQueryClient();
  const eventSourceRef = useRef(null);

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
      setAttachments([]);

      if (eventSourceRef.current) eventSourceRef.current.close();
      const es = new EventSource(`/api/convo/messages/${messageId}/stream`);
      eventSourceRef.current = es;

      es.onopen = () => {
        addMessage(threadId, { id: messageId, role: 'assistant', content: '', status: 'draft', model: variables.model, created_at: Math.floor(Date.now() / 1000) });
      };
      es.addEventListener('delta', (e) => appendStreamChunk(threadId, messageId, JSON.parse(e.data).content));
      es.addEventListener('done', (e) => {
        es.close();
        eventSourceRef.current = null;
        queryClient.invalidateQueries({ queryKey: ['messages', threadId] });
      });
      es.addEventListener('error', (e) => {
        es.close();
        eventSourceRef.current = null;
      });
    },
  });

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) eventSourceRef.current.close();
    };
  }, []);

  const handleSendMessage = (content) => {
    sendMessageMutation.mutate({
      content,
      attachments: attachments.map(a => a.id),
      model,
      temperature,
      max_tokens: maxTokens,
    });
  };

  return (
    <div className="flex flex-col h-full">
      {viewingMessageHistory && (
        <DiffViewModal
            messageId={viewingMessageHistory}
            onClose={() => setViewingMessageHistory(null)}
        />
      )}
      <div className="flex-1 overflow-y-auto p-4">
        <ChatTimeline
            messages={messages}
            isLoading={isLoading}
            error={error}
            onViewHistory={setViewingMessageHistory}
        />
      </div>
      <div className="p-4 border-t border-gray-200 dark:border-gray-700">
        <Composer
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
