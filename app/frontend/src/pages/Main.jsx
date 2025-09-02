import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import RoomHeader from '../components/RoomHeader';
import MessageList from '../components/MessageList';
import ChatInput from '../components/ChatInput';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { useAppContext } from '../context/AppContext';

const Main = ({ roomId, isSplitView = false }) => {
  const { sidebarOpen, showError } = useAppContext();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: roomData } = useQuery({
    queryKey: ['room', roomId],
    queryFn: async () => {
      if (!roomId) return null;
      const response = await axios.get(`/api/rooms/${roomId}`);
      return response.data;
    },
    enabled: !!roomId,
  });

  const createReviewMutation = useMutation({
    mutationFn: (reviewData) => axios.post(`/api/rooms/${roomId}/reviews`, reviewData),
    onSuccess: (response) => {
      const newReview = response.data;
      queryClient.invalidateQueries(['rooms']); // Invalidate rooms to show the new review room in sidebar
      // Navigate to the split view
      navigate(`/rooms/${roomId}/reviews/${newReview.review_id}`);
    },
    onError: (error) => {
      showError("Failed to start review: " + (error.response?.data?.detail || error.message));
    }
  });

  const handleStartReview = () => {
    // Simple prompt for now. Could be a modal in the future.
    const topic = prompt("Enter the topic for the review:", roomData?.name || "New Review");
    if (topic && roomData) {
      createReviewMutation.mutate({ topic, instruction: "Please analyze this topic." });
    }
  };

  const roomHeaderActions = roomData && roomData.type === 'sub' && !isSplitView ? [
    {
      label: createReviewMutation.isLoading ? "Starting..." : "Start Review",
      onClick: handleStartReview,
      variant: 'primary',
      disabled: createReviewMutation.isLoading,
    }
  ] : [];

  return (
    <div className="flex flex-col h-full bg-bg relative overflow-hidden">
      <div className="flex-shrink-0 z-10">
        <RoomHeader
          title={roomData?.name || "New Chat"}
          subtitle={roomData?.description || "Select a room or start a new conversation"}
          actions={roomHeaderActions}
          showBackButton={isSplitView}
        />
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-4 min-h-0">
        {roomId ? (
          <MessageList roomId={roomId} />
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <h1 className="text-h1 text-text mb-4">Select a room to begin</h1>
              <p className="text-body text-muted">Choose a chat from the sidebar or start a new one.</p>
            </div>
          </div>
        )}
      </div>

      <div 
        className="flex-shrink-0 border-t border-border bg-panel p-4 z-20"
        style={{
          // Adjust based on sidebar state only if not in split view
          left: !isSplitView && sidebarOpen ? '280px' : '0px',
        }}
      >
        <ChatInput roomId={roomId} disabled={!roomId || createReviewMutation.isLoading} />
      </div>
    </div>
  );
};

export default Main;
