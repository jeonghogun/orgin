import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import RoomHeader from '../components/RoomHeader';
import MessageList from '../components/MessageList';
import ChatInput from '../components/ChatInput';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { useAppContext } from '../context/AppContext';

const Review = ({ reviewId, isSplitView = false }) => {
  const { sidebarOpen } = useAppContext();
  const navigate = useNavigate();

  const { data: review, isLoading } = useQuery({
    queryKey: ['review', reviewId],
    queryFn: async () => {
      const response = await axios.get(`/api/reviews/${reviewId}`);
      return response.data;
    },
    enabled: !!reviewId,
  });

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
          subtitle={review?.instruction || 'AI Review Results'}
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

        <MessageList roomId={review?.room_id} />
      </div>

      <div 
        className="flex-shrink-0 border-t border-border bg-panel p-4 z-20"
        style={{ 
          left: !isSplitView && sidebarOpen ? '280px' : '0px',
        }}
      >
        <ChatInput roomId={review?.room_id} />
      </div>
    </div>
  );
};

export default Review;
