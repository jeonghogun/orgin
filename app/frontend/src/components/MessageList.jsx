import React, { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import useWebSocket from '../hooks/useWebSocket';

const fetchMessages = async (roomId) => {
  if (!roomId) return [];
  const { data } = await axios.get(`/api/rooms/${roomId}/messages`);
  return data || [];
};

const ThinkingBubble = () => (
  <div className="flex gap-3 justify-start">
    <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center text-white text-sm font-medium">
      A
    </div>
    <div className="max-w-[70%]">
      <div className="p-3 rounded-card bg-panel-elev border border-border text-text">
        <div className="text-body whitespace-pre-wrap">
          <div className="flex items-center space-x-2">
            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
);

const MessageList = ({ roomId }) => {
  const queryClient = useQueryClient();
  const messagesEndRef = useRef(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const handleWebSocketMessage = (eventData) => {
    if (eventData.type === 'status_update' && eventData.payload.status === 'processing') {
      setIsProcessing(true);
    } else if (eventData.type === 'new_message') {
      setIsProcessing(false);
      queryClient.setQueryData(['messages', roomId], (oldData) => {
        const newMessage = { ...eventData.payload, isNew: true };
        if (!oldData) return [newMessage];
        if (oldData.some(msg => msg.message_id === newMessage.message_id)) {
          return oldData;
        }
        return [...oldData, newMessage];
      });
    }
  };

  useWebSocket(roomId, handleWebSocketMessage);

  const { data: messages = [], isLoading } = useQuery({
    queryKey: ['messages', roomId],
    queryFn: () => fetchMessages(roomId),
    enabled: !!roomId,
  });

  useEffect(() => {
    const newMessages = messages.filter(m => m.isNew);
    if (newMessages.length > 0) {
      const timer = setTimeout(() => {
        queryClient.setQueryData(['messages', roomId], (oldData) =>
          oldData.map(m => m.isNew ? { ...m, isNew: false } : m)
        );
      }, 1500);
      return () => clearTimeout(timer);
    }
  }, [messages, roomId, queryClient]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isProcessing]);

  if (!roomId) return <div className="flex items-center justify-center h-full text-muted text-body">Select a room to start a conversation.</div>;
  if (isLoading) return <div className="flex items-center justify-center h-full text-muted">Loading messages...</div>;
  if (messages.length === 0 && !isProcessing) {
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
        <div key={message.message_id} className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
          {message.role === 'assistant' && (
            <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center text-white text-sm font-medium">A</div>
          )}
          <div className={`max-w-[70%]`}>
            <div className={`p-3 rounded-card ${message.isNew ? 'animate-flash' : ''} ${
              message.role === 'user' 
                ? 'bg-accent text-white' 
                : 'bg-panel-elev border border-border text-text'
            }`}>
              <div className="text-body whitespace-pre-wrap">{message.content}</div>
            </div>
            <div className={`text-meta text-muted mt-1 ${message.role === 'user' ? 'text-right' : 'text-left'}`}>
              {new Date(message.timestamp || Date.now()).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
            </div>
          </div>
          {message.role === 'user' && (
            <div className="w-8 h-8 rounded-full bg-accent-weak flex items-center justify-center text-white text-sm font-medium">U</div>
          )}
        </div>
      ))}
      {isProcessing && <ThinkingBubble />}
      <div ref={messagesEndRef} />
    </div>
  );
};

export default MessageList;
