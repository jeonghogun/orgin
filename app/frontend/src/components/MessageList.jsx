import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import toast from 'react-hot-toast';

import ChatInput from './ChatInput';
import Message from './Message';
import ConnectionStatusBanner from './common/ConnectionStatusBanner';
import ContextSummaryCard from './ContextSummaryCard';
import { ROOM_TYPES } from '../constants';
import useWebSocket from '../hooks/useWebSocket';


const fetchMessages = async (roomId) => {
  if (!roomId) return [];
  const { data } = await axios.get(`/api/rooms/${roomId}/messages`);
  return data || [];
};

const promoteMemory = async ({ mainRoomId, subRoomId }) => {
  const { data } = await axios.post(`/api/rooms/${mainRoomId}/promote-memory`, {
    sub_room_id: subRoomId,
    criteria_text: "Promote key learnings from this sub-room discussion.",
  });
  return data;
};

const MessageList = ({ roomId, currentRoom, createRoomMutation, interactiveReviewRoomMutation }) => {
  const messagesEndRef = useRef(null);
  const queryClient = useQueryClient();

  const promoteMemoryMutation = useMutation({
    mutationFn: promoteMemory,
    onSuccess: (data) => {
      toast.success('Memory promoted successfully!');
      // Optionally, invalidate queries if the UI should reflect the new memory
      // queryClient.invalidateQueries(['facts', currentRoom.parent_id]);
    },
    onError: (error) => {
      console.error("Failed to promote memory:", error);
      toast.error(`Error: ${error.response?.data?.detail || error.message}`);
    },
  });

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
  // The backend websocket endpoint is at /ws/rooms/{room_id} for room messages
  // We will connect if a roomId is present. The backend's AUTH_OPTIONAL=True will allow connection.
  const wsUrl = roomId ? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/rooms/${roomId}` : null;
  const { connectionStatus } = useWebSocket(wsUrl, handleNewMessage, null); // Passing null for the token


  const { data: messages = [], isLoading } = useQuery({
    queryKey: ['messages', roomId],
    queryFn: () => fetchMessages(roomId),
    enabled: !!roomId,
    staleTime: 1000 * 60 * 5, // 5 minutes
  });

  const contextMessage = useMemo(() => {
    if (!messages || messages.length === 0) {
      return null;
    }
    return messages.find((msg) => {
      if (!msg || !msg.content) return false;
      const isSystemAuthor = msg.user_id === 'system' || msg.role === 'system';
      const isAssistantSystem = msg.user_id === 'system' && msg.role !== 'user';
      const hasSummary = msg.content.includes('**핵심 요약:**') || msg.content.includes('핵심 요약');
      return (isSystemAuthor || isAssistantSystem) && hasSummary;
    }) || null;
  }, [messages]);

  const displayMessages = useMemo(() => {
    if (!contextMessage) {
      return messages;
    }
    return messages.filter((msg) => msg.message_id !== contextMessage.message_id);
  }, [messages, contextMessage]);


  useEffect(() => {
    // Scroll to bottom when new messages are added
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [displayMessages]);

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
            roomData={currentRoom}
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
      {currentRoom?.type === ROOM_TYPES.SUB && (
        <div className="flex items-center justify-between p-2 border-b border-border bg-bg-alt">
          <span className="text-sm text-muted">This is a sub-room. Learnings can be promoted to the main room.</span>
          <button
            onClick={() => {
              if (currentRoom.parent_id) {
                promoteMemoryMutation.mutate({
                  mainRoomId: currentRoom.parent_id,
                  subRoomId: currentRoom.room_id,
                });
              }
            }}
            disabled={promoteMemoryMutation.isPending}
            className="px-3 py-1 text-sm bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50"
          >
            {promoteMemoryMutation.isPending ? 'Promoting...' : 'Promote Learnings to Main Room'}
          </button>
        </div>
      )}
      <ConnectionStatusBanner status={connectionStatus} />
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {contextMessage && currentRoom?.type === ROOM_TYPES.SUB && (
          <ContextSummaryCard content={contextMessage.content} />
        )}
        {displayMessages.map((message) => (
          <Message key={message.message_id} message={message} />
        ))}
        <div ref={messagesEndRef} />
      </div>
      <div className="p-4 border-t border-border">
        <ChatInput
          roomId={roomId}
          roomData={currentRoom}
          disabled={!roomId}
          createRoomMutation={createRoomMutation}
          interactiveReviewRoomMutation={interactiveReviewRoomMutation}
        />
      </div>
    </div>
  );
};

export default MessageList;
