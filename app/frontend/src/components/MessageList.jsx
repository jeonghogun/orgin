import React, { useEffect, useRef, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import Message from './Message';
import ChatInput from './ChatInput';
import useWebSocket from '../hooks/useWebSocket';
import ConnectionStatusBanner from './common/ConnectionStatusBanner';

const fetchMessages = async (roomId) => {
  if (!roomId) return [];
  const { data } = await axios.get(`/api/rooms/${roomId}/messages`);
  return data || [];
};

const MessageList = ({ roomId, createRoomMutation, interactiveReviewRoomMutation }) => {
  const messagesEndRef = useRef(null);
  const queryClient = useQueryClient();

  const handleNewMessage = useCallback((message) => {
    // Update the query cache with the new message from WebSocket
    queryClient.setQueryData(['messages', roomId], (oldData) => {
      if (!oldData) return [message];
      // Avoid duplicates
      if (oldData.some(m => m.message_id === message.message_id)) {
        return oldData;
      }
      return [...oldData, message];
    });
  }, [queryClient, roomId]);

  // Construct WebSocket URL.
  // The backend websocket endpoint is at /api/ws/reviews/{review_id}
  // We will connect if a roomId is present. The backend's AUTH_OPTIONAL=True will allow connection.
  const wsUrl = roomId ? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/ws/reviews/${roomId}` : null;
  const { connectionStatus } = useWebSocket(wsUrl, handleNewMessage, null); // Passing null for the token


  const { data: messages = [], isLoading } = useQuery({
    queryKey: ['messages', roomId],
    queryFn: () => fetchMessages(roomId),
    enabled: !!roomId,
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
    return (
      <div className="flex flex-col h-full">
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="text-muted mb-2">No messages yet.</div>
            <div className="text-meta text-muted">Start the conversation!</div>
          </div>
        </div>
        <div className="p-4 border-t border-border">
          <ChatInput
            roomId={roomId}
            disabled={!roomId}
            createRoomMutation={createRoomMutation}
            interactiveReviewRoomMutation={interactiveReviewRoomMutation}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <ConnectionStatusBanner status={connectionStatus} />
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message) => (
          <Message key={message.message_id} message={message} />
        ))}
        <div ref={messagesEndRef} />
      </div>
      <div className="p-4 border-t border-border">
        <ChatInput
          roomId={roomId}
          disabled={!roomId}
          createRoomMutation={createRoomMutation}
          interactiveReviewRoomMutation={interactiveReviewRoomMutation}
        />
      </div>
    </div>
  );
};

export default MessageList;
