import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import RoomHeader from '../components/RoomHeader';
import MessageList from '../components/MessageList';
import ChatInput from '../components/ChatInput';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { useAppContext } from '../context/AppContext';
import useEventSource from '../hooks/useEventSource';
import toast from 'react-hot-toast';
import Message from '../components/Message'; // We need the Message component to render live messages

const Review = ({ reviewId, isSplitView = false, createRoomMutation }) => {
  const { sidebarOpen } = useAppContext();
  const navigate = useNavigate();
  const [liveMessages, setLiveMessages] = useState([]);
  const [reviewStatus, setReviewStatus] = useState('loading');

  const { data: review, isLoading } = useQuery({
    queryKey: ['review', reviewId],
    queryFn: async () => {
      const response = await axios.get(`/api/reviews/${reviewId}`);
      setReviewStatus(response.data.status);
      return response.data;
    },
    enabled: !!reviewId,
  });

  const eventHandlers = useMemo(() => ({
    live_event: (e) => {
      try {
        const eventData = JSON.parse(e.data);
        if (eventData.type === 'status_update') {
          setReviewStatus(eventData.payload.status);
        } else if (eventData.type === 'new_message') {
          setLiveMessages(prev => [...prev, eventData.payload]);
        }
      } catch (err) {
        console.error("Failed to parse live event:", err);
      }
    },
    historical_event: (e) => {
        // This is not used anymore as MessageList fetches historical messages.
        // Kept for potential future use.
    },
    error: (err) => {
      console.error("SSE Error:", err);
      toast.error("Connection to live review updates failed. Please refresh the page.");
    },
    done: () => {
      setReviewStatus('completed');
    }
  }), [reviewId]);

  const sseUrl = reviewId ? `/api/reviews/${reviewId}/events` : null;
  useEventSource(sseUrl, eventHandlers);


  // ESC key to navigate back
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        navigate(-1);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [navigate]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-text">Loading review data...</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-bg relative overflow-hidden">
      <div className="flex-shrink-0 z-10">
        <RoomHeader
          title={`Review: ${review?.topic || '...'}`}
          subtitle={`Status: ${reviewStatus}`}
          showBackButton={!isSplitView}
        />
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-4 min-h-0">
        {review?.final_report && (
          <div className="mb-6">
            <h2 className="text-h1 text-text mb-4">Final Report</h2>
            <div className="bg-panel border border-border rounded-card p-4">
              <pre className="text-body text-text whitespace-pre-wrap">{JSON.stringify(review.final_report, null, 2)}</pre>
            </div>
          </div>
        )}

        {/* MessageList will show historical messages */}
        <MessageList roomId={review?.room_id} createRoomMutation={createRoomMutation} />

        {/* Render live messages as they arrive */}
        <div className="live-messages-container">
            {liveMessages.map(msg => <Message key={msg.message_id} message={msg} />)}
        </div>
      </div>

      <div 
        className="flex-shrink-0 border-t border-border bg-panel p-4 z-20"
        style={{ 
          left: !isSplitView && sidebarOpen ? '280px' : '0px',
        }}
      >
        <ChatInput roomId={review?.room_id} createRoomMutation={createRoomMutation} disabled={reviewStatus !== 'completed'} />
      </div>
    </div>
  );
};

export default Review;
