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

const ChatWindow = ({ roomId }) => {
  const queryClient = useQueryClient();
  const [newMessage, setNewMessage] = useState('');

  const { data: messages, error, isLoading } = useQuery({
    queryKey: ['messages', roomId],
    queryFn: () => fetchMessages(roomId),
    enabled: !!roomId, // Only run the query if roomId is available
  });

  const mutation = useMutation({
    mutationFn: sendMessage,
    onSuccess: () => {
      // Invalidate and refetch the messages query after a new message is sent
      queryClient.invalidateQueries({ queryKey: ['messages', roomId] });
      setNewMessage('');
    },
  });

  const handleSendMessage = (e) => {
    e.preventDefault();
    if (!newMessage.trim()) return;
    mutation.mutate({ roomId, content: newMessage });
  };

  if (!roomId) {
    return <div className="chat-window-placeholder">Select a room to start chatting.</div>;
  }

  if (isLoading) return <div>Loading messages...</div>;
  if (error) return <div className="error">Failed to fetch messages.</div>;

  return (
    <div className="chat-window">
      <div className="message-list">
        {messages && messages.map((msg, index) => (
          <div key={index} className={`message ${msg.role}`}>
            <strong>{msg.role}:</strong> {msg.content}
          </div>
        ))}
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
