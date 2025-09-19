import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import RoomHeader from '../components/RoomHeader';
import ChatInput from '../components/ChatInput';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { useAppContext } from '../context/AppContext';
import useEventSource from '../hooks/useEventSource';
import toast from 'react-hot-toast';
import ReviewTimeline from '../components/review/ReviewTimeline';
import DebateTranscript from '../components/review/DebateTranscript';

const Review = ({ reviewId, isSplitView = false, createRoomMutation }) => {
  const { sidebarOpen } = useAppContext();
  const navigate = useNavigate();
  const [liveMessages, setLiveMessages] = useState([]);
  const [reviewStatus, setReviewStatus] = useState('loading');
  const [statusEvents, setStatusEvents] = useState([]);
  const statusKeyRef = useRef(new Set());
  const queryClient = useQueryClient();
  const [isRequestingRound, setIsRequestingRound] = useState(false);
  const MAX_DEBATE_ROUNDS = 4;
  const reviewContinuationEnabled =
    String(import.meta.env.VITE_ENABLE_REVIEW_CONTINUATION || '').toLowerCase() === 'true';

  const { data: review, isLoading } = useQuery({
    queryKey: ['review', reviewId],
    queryFn: async () => {
      const response = await axios.get(`/api/reviews/${reviewId}`);
      setReviewStatus(response.data.status);
      return response.data;
    },
    enabled: !!reviewId,
  });

  const { data: historicalMessages = [] } = useQuery({
    queryKey: ['messages', review?.room_id],
    queryFn: async () => {
      if (!review?.room_id) return [];
      const response = await axios.get(`/api/rooms/${review.room_id}/messages`);
      return response.data || [];
    },
    enabled: !!review?.room_id,
    staleTime: 1000 * 60,
  });

  const extractPersona = useCallback((message) => {
    if (!message) return '패널';
    if (message.persona) {
      return message.persona;
    }
    if (message.metadata?.persona) {
      return message.metadata.persona;
    }
    const personaMatch = message.content?.match(/Panelist:\s*([^\n]+)/i);
    if (personaMatch) {
      return personaMatch[1].trim();
    }
    if (message.user_id && message.user_id !== 'assistant') {
      return message.user_id;
    }
    return '패널';
  }, []);

  const extractRound = useCallback((message) => {
    if (!message) return null;
    if (typeof message.round === 'number') {
      return message.round;
    }
    if (message.metadata?.round) {
      return message.metadata.round;
    }
    const roundMatch = message.content?.match(/라운드\s*(\d+)/i) || message.content?.match(/Round\s*(\d+)/i);
    if (roundMatch) {
      return Number.parseInt(roundMatch[1], 10);
    }
    return null;
  }, []);

  const normalizeMessage = useCallback((message) => {
    if (!message?.message_id) return null;
    const persona = extractPersona(message);
    const round = extractRound(message);
    const rawContent = message.content || '';
    const MAX_CONTENT_LENGTH = 8000;
    const isTrimmed = rawContent.length > MAX_CONTENT_LENGTH;
    const trimmedContent = isTrimmed ? `${rawContent.slice(0, MAX_CONTENT_LENGTH)}…` : rawContent;

    return {
      ...message,
      content: trimmedContent,
      persona,
      round,
      isTrimmed,
    };
  }, [extractPersona, extractRound]);

  const appendLiveMessage = useCallback((message) => {
    const normalized = normalizeMessage(message);
    if (!normalized?.message_id) return;
    setLiveMessages((prev) => {
      if (prev.some((item) => item.message_id === normalized.message_id)) {
        return prev;
      }
      return [...prev, normalized];
    });
  }, [normalizeMessage]);

  useEffect(() => {
    statusKeyRef.current = new Set();
    setStatusEvents([]);
    setLiveMessages([]);
    setIsRequestingRound(false);
  }, [reviewId]);

  const recordStatusEvent = useCallback((status, ts) => {
    if (!status) return;
    const timestamp = typeof ts === 'number' ? ts : Math.floor(Date.now() / 1000);
    const key = `${status}-${timestamp}`;
    if (statusKeyRef.current.has(key)) {
      return;
    }
    statusKeyRef.current.add(key);
    setStatusEvents((prev) => {
      const next = [...prev, { status, timestamp }];
      next.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
      return next;
    });
  }, []);

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

  const combinedMessages = useMemo(() => {
    const map = new Map();
    const addMessage = (msg, alreadyNormalized = false) => {
      const normalized = alreadyNormalized ? msg : normalizeMessage(msg);
      if (normalized?.message_id) {
        map.set(normalized.message_id, normalized);
      }
    };
    historicalMessages.forEach((msg) => addMessage(msg));
    liveMessages.forEach((msg) => addMessage(msg, true));
    return Array.from(map.values()).sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
  }, [historicalMessages, liveMessages, normalizeMessage]);

  const personaEvents = useMemo(() => {
    const grouped = {};
    combinedMessages.forEach((message) => {
      if (!message?.content) return;
      const persona = message.persona || extractPersona(message);
      if (!grouped[persona]) {
        grouped[persona] = [];
      }
      grouped[persona].push({
        id: message.message_id,
        timestamp: message.timestamp,
        round: message.round ?? extractRound(message),
        preview: message.content.replace(/\s+/g, ' ').slice(0, 140),
      });
    });
    return grouped;
  }, [combinedMessages, extractPersona, extractRound]);

  const handleExportRecommendations = useCallback(() => {
    if (!parsedFinalReport?.recommendations?.length) {
      toast.error('다운로드할 추천 항목이 없습니다.');
      return;
    }
    const tasks = parsedFinalReport.recommendations.map((item, idx) => ({
      id: `${reviewId || review?.review_id || 'review'}-task-${idx + 1}`,
      title: `${review?.topic || '리뷰'} - 추천 ${idx + 1}`,
      description: item,
      reviewId: reviewId,
      source: 'Origin Review',
    }));
    const payload = {
      generated_at: new Date().toISOString(),
      review_id: reviewId,
      topic: review?.topic,
      tasks,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `review-${reviewId || review?.room_id}-tasks.json`;
    link.click();
    URL.revokeObjectURL(url);
    toast.success('추천 작업 템플릿을 다운로드했습니다.');
  }, [parsedFinalReport, reviewId, review]);

  const eventHandlers = useMemo(() => ({
    live_event: (e) => {
      try {
        const eventData = JSON.parse(e.data);
        if (eventData.type === 'status_update') {
          setReviewStatus(eventData.payload.status);
          recordStatusEvent(eventData.payload.status, eventData.ts);
        } else if (eventData.type === 'new_message') {
          appendLiveMessage(eventData.payload);
        }
      } catch (err) {
        console.error("Failed to parse live event:", err);
      }
    },
    historical_event: (e) => {
        try {
          const eventData = JSON.parse(e.data);
          if (eventData.type === 'status_update') {
            const statusValue = eventData.payload?.status || eventData.status;
            recordStatusEvent(statusValue, eventData.ts || eventData.timestamp);
          } else if (eventData.type === 'new_message' && eventData.payload) {
            appendLiveMessage(eventData.payload);
          }
        } catch (err) {
          console.error('Failed to parse historical event:', err);
        }
    },
    error: (err) => {
      console.error("SSE Error:", err);
      toast.error("Connection to live review updates failed. Please refresh the page.");
    },
    done: () => {
      setReviewStatus('completed');
      recordStatusEvent('completed', Math.floor(Date.now() / 1000));
    }
  }), [appendLiveMessage, recordStatusEvent, reviewId]);

  const sseUrl = reviewId ? `/api/reviews/${reviewId}/events` : null;
  useEventSource(sseUrl, eventHandlers);


  useEffect(() => {
    if (!review) return;
    if (review.created_at) {
      recordStatusEvent('created', review.created_at);
    }
    if (review.started_at) {
      recordStatusEvent('in_progress', review.started_at);
    }
    if (review.completed_at) {
      recordStatusEvent(review.status === 'failed' ? 'failed' : 'completed', review.completed_at);
    }
  }, [review, recordStatusEvent]);


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

  const roundsCompleted = review?.current_round || 0;
  const debateConcluded = roundsCompleted >= MAX_DEBATE_ROUNDS || ['completed', 'failed'].includes(reviewStatus);

  const handleRequestAnotherRound = useCallback(async () => {
    if (!reviewContinuationEnabled) {
      toast.error('추가 라운드 요청 기능은 현재 비활성화되어 있습니다.');
      return;
    }
    if (!reviewId || debateConcluded) return;
    setIsRequestingRound(true);
    try {
      await axios.post(`/api/reviews/${reviewId}/continue`);
      toast.success('추가 라운드를 요청했습니다.');
      await queryClient.invalidateQueries({ queryKey: ['review', reviewId] });
    } catch (error) {
      console.error('Failed to request additional debate round:', error);
      const detail = error.response?.data?.detail || '추가 라운드 요청에 실패했습니다.';
      toast.error(detail);
    } finally {
      setIsRequestingRound(false);
    }
  }, [debateConcluded, queryClient, reviewContinuationEnabled, reviewId]);

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
                {parsedFinalReport.recommendations.length > 0 && (
                  <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-border/60 bg-panel-elev px-3 py-2">
                    <p className="text-xs text-muted">추천 항목을 바로 작업 관리 도구로 옮길 수 있도록 JSON 템플릿을 제공합니다.</p>
                    <button
                      type="button"
                      onClick={handleExportRecommendations}
                      className="rounded-button bg-accent px-3 py-1.5 text-xs font-semibold text-white transition-colors duration-150 hover:bg-accent-weak"
                    >
                      작업 템플릿 다운로드
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        <ReviewTimeline statusEvents={statusEvents} personaEvents={personaEvents} />

        <div className="mt-6">
          <DebateTranscript
            messages={combinedMessages}
            onRequestRound={handleRequestAnotherRound}
            canRequestRound={reviewContinuationEnabled && !debateConcluded && Boolean(reviewId)}
            isRequestingRound={isRequestingRound}
            totalRoundsCompleted={roundsCompleted}
            maxRounds={MAX_DEBATE_ROUNDS}
            isDebateConcluded={debateConcluded}
            requestRoundUnavailableReason="추가 라운드 요청 기능은 현재 준비 중입니다."
          />
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
