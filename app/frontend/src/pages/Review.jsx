import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import RoomHeader from '../components/RoomHeader';
import ChatInput from '../components/ChatInput';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../lib/apiClient';
import { useAppContext } from '../context/AppContext';
import useRealtimeChannel from '../hooks/useRealtimeChannel';
import toast from 'react-hot-toast';
import TriadDiscussionFeed from '../components/review/TriadDiscussionFeed';
import useRoomsQuery from '../hooks/useRoomsQuery';

const REVIEW_STATUS_LABELS = {
  pending: '대기중',
  in_progress: '진행 중',
  completed: '완료',
  failed: '실패',
};

const Review = ({ reviewId, roomId, isSplitView = false, createRoomMutation }) => {
  const { sidebarOpen } = useAppContext();
  const navigate = useNavigate();
  const [liveMessages, setLiveMessages] = useState([]);
  const [reviewStatus, setReviewStatus] = useState('loading');
  const [statusEvents, setStatusEvents] = useState([]);
  const [selectedReviewId, setSelectedReviewId] = useState(reviewId || null);
  const statusKeyRef = useRef(new Set());
  const { data: allRooms = [] } = useRoomsQuery();
  const [sseError, setSseError] = useState(null);

  const currentRoomInfo = useMemo(
    () => allRooms.find((room) => room.room_id === roomId),
    [allRooms, roomId]
  );
  const parentRoomId = currentRoomInfo?.parent_id || null;
  const parentRoomName = useMemo(() => {
    if (!parentRoomId) return null;
    const parentRoom = allRooms.find((room) => room.room_id === parentRoomId);
    return parentRoom?.name || null;
  }, [allRooms, parentRoomId]);
  const reviewListRoomId = parentRoomId || roomId;

  const { data: roomReviews = [], isLoading: isRoomReviewsLoading } = useQuery({
    queryKey: ['roomReviews', reviewListRoomId],
    queryFn: async () => {
      if (!reviewListRoomId) return [];
      const response = await apiClient.get(`/api/rooms/${reviewListRoomId}/reviews`);
      return response.data || [];
    },
    enabled: !!reviewListRoomId,
    staleTime: 30 * 1000,
  });

  useEffect(() => {
    if (reviewId) {
      setSelectedReviewId(reviewId);
    }
  }, [reviewId]);

  useEffect(() => {
    if (reviewId) {
      return;
    }
    if (!Array.isArray(roomReviews) || roomReviews.length === 0) {
      setSelectedReviewId(null);
      return;
    }
    setSelectedReviewId((prev) => {
      if (prev && roomReviews.some((meta) => meta.review_id === prev)) {
        return prev;
      }
      return roomReviews[0].review_id;
    });
  }, [roomReviews, reviewId]);

  const effectiveReviewId = selectedReviewId;

  const { data: review, isLoading: isReviewLoading } = useQuery({
    queryKey: ['review', effectiveReviewId],
    queryFn: async () => {
      if (!effectiveReviewId) return null;
      const response = await apiClient.get(`/api/reviews/${effectiveReviewId}`);
      setReviewStatus(response.data.status);
      return response.data;
    },
    enabled: !!effectiveReviewId,
  });

  const currentReviewRoomId = review?.room_id || roomId;
  const reviewOptions = useMemo(() => {
    if (!Array.isArray(roomReviews) || roomReviews.length === 0) {
      return [];
    }
    return [...roomReviews]
      .sort((a, b) => (b.created_at || 0) - (a.created_at || 0))
      .map((meta) => {
        const topic = meta.topic || '제목 없음';
        const truncatedTopic = topic.length > 60 ? `${topic.slice(0, 57)}…` : topic;
        const statusLabel = REVIEW_STATUS_LABELS[meta.status] || meta.status;
        const timestamp = meta.created_at
          ? new Date(meta.created_at * 1000).toLocaleString()
          : null;
        const parts = [truncatedTopic];
        if (statusLabel) {
          parts.push(statusLabel);
        }
        if (timestamp) {
          parts.push(timestamp);
        }
        return {
          roomId: meta.room_id,
          reviewId: meta.review_id,
          label: parts.join(' · '),
        };
      });
  }, [roomReviews]);

  const handleReviewSwitch = useCallback(
    (event) => {
      const targetRoomId = event.target.value;
      if (!targetRoomId || targetRoomId === currentReviewRoomId) {
        return;
      }
      const targetOption = reviewOptions.find((option) => option.roomId === targetRoomId);
      if (targetOption) {
        setSelectedReviewId(targetOption.reviewId);
      }
      navigate(`/rooms/${targetRoomId}`);
    },
    [navigate, reviewOptions, currentReviewRoomId]
  );

  const { data: historicalMessages = [] } = useQuery({
    queryKey: ['messages', review?.room_id || roomId],
    queryFn: async () => {
      const targetRoomId = review?.room_id || roomId;
      if (!targetRoomId) return [];
      const response = await apiClient.get(`/api/rooms/${targetRoomId}/messages`);
      return response.data || [];
    },
    enabled: !!(review?.room_id || roomId),
    staleTime: 1000 * 60,
  });

  const reviewRoomId = currentReviewRoomId;
  const isMetaLoading = isReviewLoading || (!effectiveReviewId && isRoomReviewsLoading);

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
    const rawContent = message.content || '';
    let structuredPayload = null;
    let structuredPersona;
    let structuredRound;

    try {
      const parsed = JSON.parse(rawContent);
      if (parsed && typeof parsed === 'object') {
        if (parsed.persona) {
          structuredPersona = parsed.persona;
        }
        if (typeof parsed.round === 'number') {
          structuredRound = parsed.round;
        }
        if (parsed.payload && typeof parsed.payload === 'object') {
          structuredPayload = parsed.payload;
          if (!structuredPersona && typeof parsed.payload.persona === 'string') {
            structuredPersona = parsed.payload.persona;
          }
          if (!structuredPersona && typeof parsed.payload.panelist === 'string') {
            structuredPersona = parsed.payload.panelist;
          }
          if (
            structuredRound === undefined &&
            typeof parsed.payload.round === 'number'
          ) {
            structuredRound = parsed.payload.round;
          }
        }
      }
    } catch (error) {
      structuredPayload = null;
    }

    const persona = structuredPersona || extractPersona(message);
    const round =
      typeof structuredRound === 'number' ? structuredRound : extractRound(message);
    const MAX_CONTENT_LENGTH = 8000;
    const isTrimmed = rawContent.length > MAX_CONTENT_LENGTH;
    const trimmedContent = isTrimmed ? `${rawContent.slice(0, MAX_CONTENT_LENGTH)}…` : rawContent;

    return {
      ...message,
      content: trimmedContent,
      persona,
      round,
      isTrimmed,
      structuredPayload,
      rawContent,
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
    setReviewStatus('loading');
  }, [effectiveReviewId]);

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

  const participantNames = useMemo(() => {
    const seen = new Set();
    combinedMessages.forEach((message) => {
      if (!message) return;
      const persona = message.persona || extractPersona(message);
      if (persona && !seen.has(persona)) {
        seen.add(persona);
      }
    });
    return Array.from(seen);
  }, [combinedMessages, extractPersona]);

  const statusHistory = useMemo(() => {
    return statusEvents
      .slice(-5)
      .reverse()
      .map((event) => {
        const readable = event.timestamp
          ? new Date(event.timestamp * 1000).toLocaleString('ko-KR', {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })
          : null;
        return {
          ...event,
          label: REVIEW_STATUS_LABELS[event.status] || event.status,
          readable,
        };
      });
  }, [statusEvents]);

  const handleExportRecommendations = useCallback(() => {
    if (!parsedFinalReport?.recommendations?.length) {
      toast.error('다운로드할 추천 항목이 없습니다.');
      return;
    }
    const tasks = parsedFinalReport.recommendations.map((item, idx) => ({
      id: `${effectiveReviewId || review?.review_id || 'review'}-task-${idx + 1}`,
      title: `${review?.topic || '리뷰'} - 추천 ${idx + 1}`,
      description: item,
      reviewId: effectiveReviewId,
      source: 'Origin Review',
    }));
    const payload = {
      generated_at: new Date().toISOString(),
      review_id: effectiveReviewId,
      topic: review?.topic,
      tasks,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `review-${effectiveReviewId || review?.room_id}-tasks.json`;
    link.click();
    URL.revokeObjectURL(url);
    toast.success('추천 작업 템플릿을 다운로드했습니다.');
  }, [effectiveReviewId, parsedFinalReport, review]);

  const eventHandlers = useMemo(() => ({
    live_event: (envelope) => {
      if (!envelope) return;
      if (envelope.type === 'status_update' && envelope.payload?.status) {
        setReviewStatus(envelope.payload.status);
        recordStatusEvent(envelope.payload.status, envelope.meta?.ts || envelope.payload.ts);
      } else if (envelope.type === 'new_message' && envelope.payload) {
        appendLiveMessage(envelope.payload);
      }
    },
    historical_event: (envelope) => {
      if (!envelope) return;
      if (envelope.type === 'status_update') {
        const statusValue = envelope.payload?.status || envelope.status;
        recordStatusEvent(statusValue, envelope.meta?.ts || envelope.payload?.ts || envelope.timestamp);
      } else if (envelope.type === 'new_message' && envelope.payload) {
        appendLiveMessage(envelope.payload);
      }
    },
    heartbeat: () => {},
    done: () => {
      setReviewStatus('completed');
      recordStatusEvent('completed', Math.floor(Date.now() / 1000));
    }
  }), [appendLiveMessage, recordStatusEvent]);

  const sseUrl = effectiveReviewId ? `/api/reviews/${effectiveReviewId}/events` : null;
  const { status: connectionStatus, reconnect: reconnectStream } = useRealtimeChannel({
    url: sseUrl,
    events: eventHandlers,
    onError: (error) => {
      console.error('SSE Error:', error);
      setSseError(error?.message || '실시간 검토 업데이트 연결이 끊어졌습니다.');
      toast.error('실시간 검토 업데이트 연결이 끊어졌습니다. 다시 연결을 시도해주세요.');
    },
  });

  const shouldShowReconnectNotice = useMemo(
    () => Boolean(sseError) || ['failed', 'disconnected', 'reconnecting'].includes(connectionStatus),
    [connectionStatus, sseError]
  );

  const handleReconnectClick = useCallback(() => {
    setSseError(null);
    reconnectStream?.();
  }, [reconnectStream]);

  useEffect(() => {
    if (connectionStatus === 'connected' || connectionStatus === 'completed' || connectionStatus === 'idle') {
      setSseError(null);
    }
  }, [connectionStatus]);


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

  if (isMetaLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-text">Loading review data...</div>
      </div>
    );
  }

  if (!effectiveReviewId) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-text">
          <p className="text-body">이 룸과 연결된 검토 정보를 찾을 수 없습니다.</p>
          <p className="text-meta text-muted mt-2">검토가 아직 생성 중이거나 초기화되지 않았을 수 있습니다.</p>
        </div>
      </div>
    );
  }

  if (!review && !isReviewLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-text">검토 세부 정보를 불러오지 못했습니다.</div>
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

      {shouldShowReconnectNotice && (
        <div className="px-4 pt-3">
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
            <span className="flex-1 min-w-[220px]">
              {connectionStatus === 'reconnecting'
                ? '실시간 업데이트에 다시 연결 중입니다...'
                : sseError || '실시간 업데이트 연결이 끊어졌습니다.'}
            </span>
            <button
              type="button"
              onClick={handleReconnectClick}
              disabled={connectionStatus === 'reconnecting'}
              className="rounded-md border border-danger/40 px-3 py-1 text-xs font-semibold text-danger hover:bg-danger/10 focus-ring disabled:cursor-not-allowed disabled:opacity-60"
            >
              다시 연결
            </button>
          </div>
        </div>
      )}

      {reviewOptions.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 bg-panel/40 px-4 py-3">
          <div className="text-xs text-muted">
            {parentRoomName
              ? `연결된 세부룸: ${parentRoomName}`
              : '검토 세션을 선택하여 다른 실행 결과를 확인할 수 있습니다.'}
          </div>
          <div className="flex items-center gap-2">
            <label
              htmlFor="review-session-select"
              className="text-[11px] font-semibold uppercase tracking-wide text-muted"
            >
              Review Session
            </label>
            <select
              id="review-session-select"
              value={currentReviewRoomId || ''}
              onChange={handleReviewSwitch}
              disabled={reviewOptions.length === 1}
              className="rounded-md border border-border bg-panel px-3 py-1.5 text-sm text-text shadow-sm transition focus:outline-none focus:ring-2 focus:ring-accent disabled:cursor-not-allowed disabled:opacity-60"
            >
              {reviewOptions.map((option) => (
                <option key={option.reviewId} value={option.roomId}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-4 pb-6 min-h-0">
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
          <section className="rounded-card border border-border bg-panel p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="space-y-1">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted">검토 주제</p>
                <h1 className="text-h1 text-text">{review?.topic || '세션 정보를 불러오는 중입니다.'}</h1>
                {review?.instruction && (
                  <p className="text-sm text-muted">{review.instruction}</p>
                )}
              </div>
              <div className="flex flex-col items-end gap-3 text-right">
                <span className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1 text-xs font-semibold text-muted">
                  상태: {REVIEW_STATUS_LABELS[reviewStatus] || reviewStatus}
                </span>
                {participantNames.length > 0 && (
                  <div className="flex flex-wrap justify-end gap-2">
                    {participantNames.map((name) => (
                      <span
                        key={name}
                        className="rounded-full bg-border/40 px-3 py-1 text-[11px] font-medium text-muted"
                      >
                        {name}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
            {statusHistory.length > 0 && (
              <div className="mt-4 border-t border-border/60 pt-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted">진행 기록</p>
                <ul className="mt-2 flex flex-wrap gap-3 text-xs text-muted">
                  {statusHistory.map((event, idx) => (
                    <li key={`status-${event.status}-${event.timestamp}-${idx}`} className="flex items-center gap-2">
                      <span className="font-semibold text-text">{event.label}</span>
                      {event.readable && <span>{event.readable}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          <TriadDiscussionFeed messages={combinedMessages} />

          {parsedFinalReport && (
            <section className="rounded-card border border-border bg-panel p-6 space-y-4">
              <header className="space-y-1">
                <h2 className="text-h2 text-text">관찰자 최종 정리</h2>
                <p className="text-sm text-muted">세 패널의 합의와 실행 계획을 한눈에 볼 수 있습니다.</p>
              </header>
              <div className="space-y-3 text-body text-muted">
                <div className="rounded-md bg-border/10 px-4 py-3 text-text">
                  {parsedFinalReport.summary || '요약 정보가 아직 제공되지 않았습니다.'}
                </div>
                <div className="grid gap-4 md:grid-cols-3">
                  <div className="space-y-2">
                    <p className="text-sm font-semibold text-text">강한 합의</p>
                    {parsedFinalReport.consensus.length > 0 ? (
                      <ul className="list-disc list-inside space-y-1">
                        {parsedFinalReport.consensus.map((item, idx) => (
                          <li key={`consensus-${idx}`}>{item}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-sm text-muted">기록된 합의가 없습니다.</p>
                    )}
                  </div>
                  <div className="space-y-2">
                    <p className="text-sm font-semibold text-text">남은 쟁점</p>
                    {parsedFinalReport.disagreements.length > 0 ? (
                      <ul className="list-disc list-inside space-y-1">
                        {parsedFinalReport.disagreements.map((item, idx) => (
                          <li key={`disagreement-${idx}`}>{item}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-sm text-muted">추가로 논의할 쟁점이 없습니다.</p>
                    )}
                  </div>
                  <div className="space-y-2">
                    <p className="text-sm font-semibold text-text">우선 실행 제안</p>
                    {parsedFinalReport.recommendations.length > 0 ? (
                      <ul className="list-disc list-inside space-y-1">
                        {parsedFinalReport.recommendations.map((item, idx) => (
                          <li key={`recommendation-${idx}`}>{item}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-sm text-muted">추가 실행 제안이 없습니다.</p>
                    )}
                  </div>
                </div>
                {parsedFinalReport.recommendations.length > 0 && (
                  <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border/60 bg-panel-elev px-3 py-2">
                    <p className="text-xs text-muted">추천 항목을 그대로 작업 관리 도구로 옮길 수 있도록 JSON 템플릿을 제공합니다.</p>
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
            </section>
          )}
        </div>
      </div>

      <div 
        className="flex-shrink-0 border-t border-border bg-panel p-4 z-20"
        style={{ 
          left: !isSplitView && sidebarOpen ? '280px' : '0px',
        }}
      >
        <ChatInput roomId={reviewRoomId} createRoomMutation={createRoomMutation} disabled={reviewStatus !== 'completed'} />
      </div>
    </div>
  );
};

export default Review;
