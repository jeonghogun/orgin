import React, { useState, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { SSE } from 'sse.js';
import { useAppContext } from '../context/AppContext';

// This function is now a pure API call that returns a Promise
// It takes callbacks to report progress back to the component.
const streamMessageApi = ({ roomId, content, onChunk, onIdReceived }) => {
  return new Promise((resolve, reject) => {
    const source = new SSE(`/api/rooms/${roomId}/messages/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      payload: JSON.stringify({ content }),
    });

    source.addEventListener('message', (e) => {
      if (e.data === '[DONE]') {
        source.close();
        resolve(); // Resolve the promise when the stream is done
        return;
      }
      try {
        const data = JSON.parse(e.data);
        if (data.delta) {
          onChunk(data.delta);
        }
        if (data.done) {
          onIdReceived(data.message_id);
        }
        if (data.error) {
          source.close();
          reject(new Error(data.error));
        }
      } catch (err) {
        source.close();
        reject(new Error('스트리밍 데이터를 파싱하는 중 오류가 발생했습니다.'));
      }
    });

    source.addEventListener('error', (e) => {
      source.close();
      reject(new Error('연결 오류가 발생했습니다. 다시 시도해주세요.'));
    });

    source.stream();
  });
};

const uploadFileApi = async ({ roomId, file }) => {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await axios.post(`/api/rooms/${roomId}/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
};

const ChatInput = ({ roomId, disabled = false }) => {
  const [message, setMessage] = useState('');
  const fileInputRef = useRef(null);
  const queryClient = useQueryClient();
  const { showError } = useAppContext();

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

    // --- Manual Optimistic Update ---
    // 1. Create temporary IDs for the optimistic messages
    const tempUserId = `temp-user-${Date.now()}`;
    const tempAssistantId = `temp-assistant-${Date.now()}`;

    // 2. Add the user message and assistant placeholder to the cache
    queryClient.setQueryData(['messages', roomId], (old) => [
      ...(old || []),
      {
        message_id: tempUserId,
        role: 'user',
        content: message,
        timestamp: Math.floor(Date.now() / 1000),
      },
      {
        message_id: tempAssistantId,
        role: 'assistant',
        content: '',
        timestamp: Math.floor(Date.now() / 1000),
        isStreaming: true,
      },
    ]);
    // --- End of Optimistic Update ---

    streamMutation.mutate({
      roomId,
      content: message,
      // 3. Define callbacks to update the streaming message in the cache
      onChunk: (delta) => {
        queryClient.setQueryData(['messages', roomId], (old) =>
          old.map((msg) =>
            msg.message_id === tempAssistantId
              ? { ...msg, content: msg.content + delta }
              : msg
          )
        );
      },
      onIdReceived: (finalId) => {
        queryClient.setQueryData(['messages', roomId], (old) =>
          old.map((msg) =>
            msg.message_id === tempAssistantId
              ? { ...msg, isStreaming: false, message_id: finalId }
              : msg
          )
        );
      },
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
      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        disabled={disabled || uploadMutation.isPending || streamMutation.isPending}
        className="p-2 text-muted hover:text-text transition-colors duration-150 focus-ring disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14m-7-7h14"/></svg>
      </button>
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileSelect}
        className="hidden"
        accept="image/*,.pdf,.doc,.docx,.txt"
      />

      <form onSubmit={handleSubmit} className="flex-1 relative">
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
