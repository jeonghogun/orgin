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

  const parsedFinalReport = useMemo(() => {
    if (!review?.final_report) return null;
    const report = review.final_report;
    return {
      summary: report.executive_summary || report.summary || '',
      consensus: report.strongest_consensus || report.consensus || [],
      disagreements: report.remaining_disagreements || report.disagreements || [],
      recommendations: report.recommendations || report.action_items || [],
    };
  }, [review?.final_report]);

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
        {parsedFinalReport && (
          <div className="mb-6">
            <h2 className="text-h1 text-text mb-4">관찰자 최종 보고서</h2>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="md:col-span-2 bg-panel border border-border rounded-card p-4">
                <h3 className="text-h2 text-text mb-2">종합 요약</h3>
                <p className="text-body text-muted whitespace-pre-wrap leading-relaxed">
                  {parsedFinalReport.summary || '요약 정보가 아직 제공되지 않았습니다.'}
                </p>
              </div>

              <div className="bg-panel border border-border rounded-card p-4">
                <h3 className="text-h3 text-text mb-2">강한 합의</h3>
                {parsedFinalReport.consensus.length > 0 ? (
                  <ul className="list-disc list-inside space-y-1 text-body text-muted">
                    {parsedFinalReport.consensus.map((item, idx) => (
                      <li key={`consensus-${idx}`}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-body text-muted">특별한 합의 사항이 기록되지 않았습니다.</p>
                )}
              </div>

              <div className="bg-panel border border-border rounded-card p-4">
                <h3 className="text-h3 text-text mb-2">남은 쟁점</h3>
                {parsedFinalReport.disagreements.length > 0 ? (
                  <ul className="list-disc list-inside space-y-1 text-body text-muted">
                    {parsedFinalReport.disagreements.map((item, idx) => (
                      <li key={`disagreement-${idx}`}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-body text-muted">추가 논의가 필요한 쟁점이 없습니다.</p>
                )}
              </div>

              <div className="md:col-span-2 bg-panel border border-border rounded-card p-4">
                <h3 className="text-h3 text-text mb-2">우선 실행 제안</h3>
                {parsedFinalReport.recommendations.length > 0 ? (
                  <ol className="list-decimal list-inside space-y-1 text-body text-muted">
                    {parsedFinalReport.recommendations.map((item, idx) => (
                      <li key={`recommendation-${idx}`}>{item}</li>
                    ))}
                  </ol>
                ) : (
                  <p className="text-body text-muted">추가 실행 제안이 없습니다.</p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* MessageList will show historical messages */}
        <MessageList roomId={review?.room_id} createRoomMutation={createRoomMutation} />

        {/* Render live messages as they arrive */}
        {liveMessages.length > 0 && (
          <div className="mt-6 space-y-4" aria-live="polite">
            {liveMessages.map((msg) => (
              <Message key={msg.message_id} message={msg} />
            ))}
          </div>
        )}
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
