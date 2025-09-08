import React, { useEffect, useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { useMessages, useConversationActions, useGenerationSettings } from '../../store/useConversationStore';
import RoomHeader from '../RoomHeader';
import ChatTimeline from './ChatTimeline';
import Composer from './Composer';
import DiffViewModal from './DiffViewModal';

const ChatView = ({ threadId }) => {
  const [attachments, setAttachments] = useState([]);
  const [viewingMessageHistory, setViewingMessageHistory] = useState(null);
  const [exportJob, setExportJob] = useState(null);
  const messages = useMessages(threadId);
  const { setMessages, addMessage, appendStreamChunk, updateMessage } = useConversationActions();
  const { model, temperature, maxTokens } = useGenerationSettings();
  const queryClient = useQueryClient();
  const eventSourceRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);
  const maxReconnectAttempts = 5;

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
      es.addEventListener('delta', (e) => {
        try {
          if (!e.data || e.data.trim() === '') {
            console.warn('Empty SSE data received');
            return;
          }
          const data = JSON.parse(e.data);
          const content = data.content || data.text || data || '';
          if (content) {
            appendStreamChunk(threadId, messageId, content);
          }
        } catch (error) {
          console.error('Error parsing streaming data:', error, 'Raw data:', e.data);
          // Don't show modal, just log the error
        }
      });
      es.addEventListener('done', (e) => {
        es.close();
        eventSourceRef.current = null;
        queryClient.invalidateQueries({ queryKey: ['messages', threadId] });
      });
      es.addEventListener('error', (e) => {
        console.error('SSE connection error:', e);
        es.close();
        eventSourceRef.current = null;
        
        // Attempt to reconnect with exponential backoff
        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          const delay = Math.pow(2, reconnectAttemptsRef.current) * 1000; // 1s, 2s, 4s, 8s, 16s
          console.log(`Attempting to reconnect in ${delay}ms (attempt ${reconnectAttemptsRef.current + 1}/${maxReconnectAttempts})`);
          
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttemptsRef.current++;
            // Reconnect by creating a new EventSource
            const newEs = new EventSource(`/api/convo/messages/${messageId}/stream`);
            eventSourceRef.current = newEs;
            
            newEs.onopen = () => {
              console.log('SSE reconnected successfully');
              reconnectAttemptsRef.current = 0; // Reset on successful connection
            };
            
            newEs.addEventListener('delta', (e) => {
              try {
                if (!e.data || e.data.trim() === '') {
                  console.warn('Empty SSE data received');
                  return;
                }
                const data = JSON.parse(e.data);
                const content = data.content || data.text || data || '';
                if (content) {
                  appendStreamChunk(threadId, messageId, content);
                }
              } catch (error) {
                console.error('Error parsing streaming data:', error, 'Raw data:', e.data);
                // Don't show modal, just log the error
              }
            });
            newEs.addEventListener('done', (e) => {
              newEs.close();
              eventSourceRef.current = null;
              queryClient.invalidateQueries({ queryKey: ['messages', threadId] });
            });
            newEs.addEventListener('error', (e) => {
              console.error('SSE reconnection error:', e);
              newEs.close();
              eventSourceRef.current = null;
              
              // Continue with exponential backoff
              if (reconnectAttemptsRef.current < maxReconnectAttempts) {
                const delay = Math.pow(2, reconnectAttemptsRef.current) * 1000;
                console.log(`Retrying reconnection in ${delay}ms (attempt ${reconnectAttemptsRef.current + 1}/${maxReconnectAttempts})`);
                
                reconnectTimeoutRef.current = setTimeout(() => {
                  reconnectAttemptsRef.current++;
                  // Recursive retry
                  const retryEs = new EventSource(`/api/convo/messages/${messageId}/stream`);
                  eventSourceRef.current = retryEs;
                  
                  retryEs.onopen = () => {
                    console.log('SSE reconnected successfully');
                    reconnectAttemptsRef.current = 0;
                  };
                  
                  retryEs.addEventListener('delta', (e) => {
                    try {
                      if (!e.data || e.data.trim() === '') {
                        console.warn('Empty SSE data received');
                        return;
                      }
                      const data = JSON.parse(e.data);
                      const content = data.content || data.text || data || '';
                      if (content) {
                        appendStreamChunk(threadId, messageId, content);
                      }
                    } catch (error) {
                      console.error('Error parsing streaming data:', error, 'Raw data:', e.data);
                      // Don't show modal, just log the error
                    }
                  });
                  retryEs.addEventListener('done', (e) => {
                    retryEs.close();
                    eventSourceRef.current = null;
                    queryClient.invalidateQueries({ queryKey: ['messages', threadId] });
                  });
                  retryEs.addEventListener('error', (e) => {
                    console.error('SSE final reconnection error:', e);
                    retryEs.close();
                    eventSourceRef.current = null;
                    if (reconnectAttemptsRef.current >= maxReconnectAttempts) {
                      console.error('Max reconnection attempts reached. Giving up.');
                    }
                  });
                }, delay);
              } else {
                console.error('Max reconnection attempts reached. Giving up.');
              }
            });
          }, delay);
        } else {
          console.error('Max reconnection attempts reached. Giving up.');
        }
      });
    },
  });

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) eventSourceRef.current.close();
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
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

  const createExportJobMutation = useMutation({
    mutationFn: (format) => axios.post(`/api/threads/${threadId}/export/jobs`, null, { params: { format } }),
    onSuccess: (response) => {
      setExportJob(response.data);
    },
    onError: (error) => {
      console.error("Failed to start export job", error);
      // You might want to show a toast notification here
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
    refetchInterval: (query) => {
      const data = query.state.data;
      return (data?.status === 'queued' || data?.status === 'processing') ? 2000 : false;
    },
    enabled: !!exportJob && (exportJob.status === 'queued' || exportJob.status === 'processing'),
  });

  const headerActions = [
    {
      label: 'Export as ZIP',
      onClick: () => createExportJobMutation.mutate('zip'),
      variant: 'secondary',
    }
  ];

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
