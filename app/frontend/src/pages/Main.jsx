import React, { useState, useEffect, useCallback } from 'react';
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

  const { data: rooms = [] } = useQuery({
    queryKey: ['rooms'],
    queryFn: async () => {
      const response = await axios.get('/api/rooms');
      return response.data;
    },
  });

  const { data: roomData } = useQuery({
    queryKey: ['room', roomId],
    queryFn: async () => {
      if (!roomId) return null;
      const response = await axios.get(`/api/rooms/${roomId}`);
      return response.data;
    },
    enabled: !!roomId,
  });

  // 메인룸이 없고 roomId도 없으면 메인룸으로 리다이렉트
  const mainRoom = rooms.find(room => room.type === 'main');
  useEffect(() => {
    if (!isSplitView && !roomId && mainRoom) {
      navigate(`/rooms/${mainRoom.room_id}`, { replace: true });
    }
  }, [roomId, mainRoom, navigate, isSplitView]);

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

  const createRoomMutation = useMutation({
    mutationFn: async ({ name, type, parentId }) => {
      const { data } = await axios.post('/api/rooms', { name, type, parent_id: parentId });
      return data;
    },
    onSuccess: (newRoom) => {
      queryClient.invalidateQueries({ queryKey: ['rooms'] });
      navigate(`/rooms/${newRoom.room_id}`);
    },
    onError: (error) => {
      showError('룸 생성에 실패했습니다: ' + (error.response?.data?.detail || error.message));
    },
  });

  const handleCreateSubRoom = useCallback((parentId) => {
    const roomName = prompt('새 세부룸의 이름을 입력하세요:', '새 세부룸');
    if (roomName && roomName.trim()) {
      createRoomMutation.mutate({ 
        name: roomName.trim(), 
        type: 'sub', 
        parentId 
      });
    }
  }, [createRoomMutation]);

  const handleCreateReviewRoom = useCallback((parentId) => {
    const topic = prompt('어떤 주제로 검토룸을 만들까요?', '');
    if (topic && topic.trim()) {
      createRoomMutation.mutate({ 
        name: topic.trim(), 
        type: 'review', 
        parentId 
      });
    }
  }, [createRoomMutation]);

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
              <h1 className="text-h1 text-text mb-4">메인룸으로 시작하세요</h1>
              <p className="text-body text-muted">왼쪽 사이드바에서 메인룸을 선택하거나, 메인룸이 자동으로 생성됩니다.</p>
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
        <ChatInput 
          roomId={roomId} 
          roomData={roomData}
          disabled={!roomId || createReviewMutation.isLoading} 
          onCreateSubRoom={handleCreateSubRoom}
          onCreateReviewRoom={handleCreateReviewRoom}
        />
      </div>
    </div>
  );
};

export default Main;
