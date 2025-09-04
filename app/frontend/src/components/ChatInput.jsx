import React, { useState, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';

import { SSE } from 'sse.js';

const streamMessage = async ({ roomId, content, queryClient, showError, onStreamEnd }) => {
  // Optimistically add user message
  const userMessage = {
    message_id: `temp-user-${Date.now()}`,
    role: 'user',
    content: content,
    timestamp: Math.floor(Date.now() / 1000),
  };
  queryClient.setQueryData(['messages', roomId], (old) => [...(old || []), userMessage]);

  // Add a placeholder for the AI response
  const assistantMessageId = `temp-assistant-${Date.now()}`;
  const assistantMessage = {
    message_id: assistantMessageId,
    role: 'assistant',
    content: '',
    timestamp: Math.floor(Date.now() / 1000),
    isStreaming: true,
  };
  queryClient.setQueryData(['messages', roomId], (old) => [...(old || []), assistantMessage]);

  const source = new SSE(`/api/rooms/${roomId}/messages/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    payload: JSON.stringify({ content }),
  });

  source.addEventListener('message', (e) => {
    if (e.data === '[DONE]') {
      source.close();
      return;
    }

    try {
      const data = JSON.parse(e.data);
      if (data.delta) {
        queryClient.setQueryData(['messages', roomId], (old) =>
          old.map((msg) =>
            msg.message_id === assistantMessageId
              ? { ...msg, content: msg.content + data.delta }
              : msg
          )
        );
      }
      if (data.done) {
        queryClient.setQueryData(['messages', roomId], (old) =>
          old.map((msg) =>
            msg.message_id === assistantMessageId
              ? { ...msg, isStreaming: false, message_id: data.message_id }
              : msg
          )
        );
        source.close();
        if (onStreamEnd) onStreamEnd();
      }
      if (data.error) {
        showError(data.error);
        source.close();
        if (onStreamEnd) onStreamEnd();
      }
    } catch (err) {
      console.error('Error parsing stream data:', err);
      showError('스트리밍 데이터를 파싱하는 중 오류가 발생했습니다.');
      source.close();
      if (onStreamEnd) onStreamEnd();
    }
  });

  source.addEventListener('error', (e) => {
    console.error('SSE Error:', e);
    showError('연결 오류가 발생했습니다. 다시 시도해주세요.');
    // Clean up the streaming message
     queryClient.setQueryData(['messages', roomId], (old) =>
        old.filter(msg => msg.message_id !== assistantMessageId)
     );
    if (onStreamEnd) onStreamEnd();
  });

  source.stream();
  return source; // Return the source object to allow for cancellation
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
  const [sseSource, setSseSource] = useState(null);
  const fileInputRef = useRef(null);
  const queryClient = useQueryClient();
  const { showError } = useAppContext();

  const isStreaming = sseSource !== null;

  const streamMutation = useMutation({
    mutationFn: streamMessage,
    onSuccess: (source) => {
      setSseSource(source);
    },
    onError: (error) => {
      console.error("Mutation Error:", error);
      showError("스트리밍 시작에 실패했습니다.");
      setSseSource(null);
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
    if (!message.trim() || !roomId || streamMutation.isLoading || isStreaming || disabled) return;

    const onStreamEnd = () => {
      setSseSource(null);
      queryClient.invalidateQueries({ queryKey: ['messages', roomId] });
    };

    streamMutation.mutate({ roomId, content: message, queryClient, showError, onStreamEnd });
    setMessage('');
  };

  const handleStop = () => {
    if (sseSource) {
      sseSource.close();
      setSseSource(null);
    }
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

      {isStreaming ? (
        <button
          type="button"
          onClick={handleStop}
          className="btn-secondary px-4 py-2 rounded-button flex items-center gap-2"
        >
          <svg className="w-4 h-4" viewBox="0 0 16 16" fill="currentColor">
            <rect width="16" height="16" rx="2"></rect>
          </svg>
          생성 중단
        </button>
      ) : (
        <>
          {/* 메시지 입력 필드 */}
          <form onSubmit={handleSubmit} className="flex-1">
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
              placeholder={disabled ? "룸을 선택해주세요" : "무엇이든 물어보세요..."}
              disabled={disabled || streamMutation.isLoading || isUploading}
              className="w-full px-4 py-3 bg-panel-elev border border-border rounded-input text-body text-text placeholder-muted focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent disabled:opacity-50 disabled:cursor-not-allowed resize-none"
              rows={1}
            />
          </form>

          {/* 전송 버튼 */}
          <button
            type="submit"
            onClick={handleSubmit}
            disabled={!message.trim() || !roomId || streamMutation.isLoading || isUploading || disabled}
            className="p-3 bg-accent hover:bg-accent-weak text-white rounded-button transition-colors duration-150 focus-ring disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M22 2L11 13M22 2L15 22L11 13M22 2L2 9L11 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </>
      )}

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
