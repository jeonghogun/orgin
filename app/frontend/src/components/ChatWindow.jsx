import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';

const fetchMessages = async (roomId) => {
  if (!roomId) return [];
  const { data } = await axios.get(`/api/rooms/${roomId}/messages`);
  return data;
};

const sendMessage = async ({ roomId, content }) => {
  const { data } = await axios.post(`/api/rooms/${roomId}/messages`, { content });
  return data.response;
};

import LoadingSpinner from './common/LoadingSpinner';
import ErrorMessage from './common/ErrorMessage';
import EmptyState from './common/EmptyState';

const ChatWindow = ({ roomId }) => {
  const queryClient = useQueryClient();
  const [newMessage, setNewMessage] = useState('');

  const { data: messages, error, isLoading } = useQuery({
    queryKey: ['messages', roomId],
    queryFn: () => fetchMessages(roomId),
    enabled: !!roomId,
  });

  const mutation = useMutation({
    mutationFn: sendMessage,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['messages', roomId] });
      setNewMessage('');
    },
  });

  const handleSendMessage = (e) => {
    e.preventDefault();
    if (!newMessage.trim()) return;
    mutation.mutate({ roomId, content: newMessage });
  };

  const renderMessages = () => {
    if (isLoading) return <LoadingSpinner />;
    if (error) return <ErrorMessage error={error} message="Failed to fetch messages." />;
    if (!messages || messages.length === 0) {
      return <EmptyState message="No messages yet. Send one to start the conversation." />;
    }
    return messages.map((msg, index) => (
      <div key={index} className={`message ${msg.role}`}>
        <strong>{msg.role}:</strong> {msg.content}
      </div>
    ));
  };

  const handleExport = async (format) => {
    if (!roomId) return;
    try {
      const response = await axios.get(`/api/rooms/${roomId}/export?format=${format}`, {
        responseType: format === 'markdown' ? 'blob' : 'json',
      });

      if (format === 'markdown') {
        const url = window.URL.createObjectURL(new Blob([response.data]));
        const link = document.createElement('a');
        link.href = url;
        const roomName = 'export'; // In a real app, get room name from state
        link.setAttribute('download', `export_room_${roomId}_${Date.now()}.md`);
        document.body.appendChild(link);
        link.click();
        link.remove();
      } else {
        // For JSON, maybe open in new tab or copy to clipboard
        const jsonString = JSON.stringify(response.data, null, 2);
        const blob = new Blob([jsonString], { type: 'application/json' });
        const url = window.URL.createObjectURL(blob);
        window.open(url, '_blank');
      }
    } catch (err) {
      console.error(`Failed to export as ${format}`, err);
      alert(`Failed to export as ${format}.`);
    }
  };

  if (!roomId) {
    return <div className="chat-window-placeholder"><EmptyState message="Select a room to start chatting." /></div>;
  }

  return (
    <div className="chat-window">
      <div className="chat-header">
        <span>Room: {roomId}</span>
        <div className="export-buttons">
          <button onClick={() => handleExport('json')}>Export JSON</button>
          <button onClick={() => handleExport('markdown')}>Export Markdown</button>
        </div>
      </div>
      <div className="message-list">
        {renderMessages()}
      </div>
      <form onSubmit={handleSendMessage} className="message-form">
        <input
          type="text"
          value={newMessage}
          onChange={(e) => setNewMessage(e.target.value)}
          placeholder="Type your message..."
          disabled={mutation.isLoading}
        />
        <button type="submit" disabled={mutation.isLoading}>
          {mutation.isLoading ? 'Sending...' : 'Send'}
        </button>
      </form>
      {mutation.isError && <div className="error">Failed to send message.</div>}
    </div>
  );
};

export default ChatWindow;
