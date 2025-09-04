import React, { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import Message from './Message'; // Import the new component

const fetchMessages = async (roomId) => {
  if (!roomId) return [];
  const { data } = await axios.get(`/api/rooms/${roomId}/messages`);
  return data || [];
};

const MessageList = ({ roomId }) => {
  const messagesEndRef = useRef(null);

  const { data: messages = [], isLoading } = useQuery({
    queryKey: ['messages', roomId],
    queryFn: () => fetchMessages(roomId),
    enabled: !!roomId,
    // The streaming logic in ChatInput will update this query's cache,
    // so we don't need to refetch as frequently.
    staleTime: 1000 * 60 * 5, // 5 minutes
  });

  useEffect(() => {
    // Scroll to bottom when new messages are added
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (!roomId) {
    // TODO: Replace with example prompts component
    return <div className="flex items-center justify-center h-full text-muted text-body">Select a room to start a conversation.</div>;
  }

  if (isLoading) {
    return <div className="flex items-center justify-center h-full text-muted">Loading messages...</div>;
  }

  if (messages.length === 0) {
     // TODO: Replace with example prompts component
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="text-muted mb-2">No messages yet.</div>
          <div className="text-meta text-muted">Start the conversation!</div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {messages.map((message) => (
        <Message key={message.message_id} message={message} />
      ))}
      <div ref={messagesEndRef} />
    </div>
  );
};

export default MessageList;
