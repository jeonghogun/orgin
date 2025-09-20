import React, { useState, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';

import { useQuery } from '@tanstack/react-query';
import LoadingSpinner from './common/LoadingSpinner';
import ErrorMessage from './common/ErrorMessage';
import useRealtimeChannel from '../hooks/useRealtimeChannel';
import { withFallbackMeta } from '../utils/realtime';

const fetchReport = async (reviewId) => {
  const { data } = await axios.get(`/api/reviews/${reviewId}/report`);
  return data.data;
};

const ReviewPanel = () => {
  const { reviewId } = useParams();
  const [reviewStatus, setReviewStatus] = useState('pending');
  const [socketError, setSocketError] = useState(null);

  const eventHandlers = useMemo(() => ({
    live_event: (envelope) => {
      if (!envelope) return;
      const normalized = withFallbackMeta(envelope);
      if (normalized.type === 'status_update' && normalized.payload?.status) {
        setReviewStatus(normalized.payload.status);
      }
    },
    historical_event: (envelope) => {
      if (!envelope) return;
      const normalized = withFallbackMeta(envelope);
      if (normalized.type === 'status_update' && normalized.payload?.status) {
        setReviewStatus(normalized.payload.status);
      }
    },
  }), []);

  const sseUrl = reviewId ? `/api/reviews/${reviewId}/events` : null;
  const { status: connectionStatus } = useRealtimeChannel({
    url: sseUrl,
    events: eventHandlers,
    onError: (error) => {
      setSocketError(error.message || 'An unknown stream error occurred.');
    },
  });

  const { data: report, isLoading: isReportLoading, error: reportError } = useQuery({
    queryKey: ['reviewReport', reviewId],
    queryFn: () => fetchReport(reviewId),
    enabled: reviewStatus === 'completed', // Only fetch when the review is complete
    retry: 3,
  });

  const renderReport = () => {
    if (reviewStatus !== 'completed') {
      return <p>Waiting for review to complete... Current status: <strong>{reviewStatus}</strong></p>;
    }
    if (isReportLoading) {
      return <LoadingSpinner />;
    }
    if (reportError) {
      return <ErrorMessage error={reportError} message="Failed to load final report." />;
    }
    if (report) {
      return (
        <>
          <hr />
          <h2>Review Report</h2>
          <h3>{report.topic}</h3>
          <div className="report-section">
            <h4>Executive Summary</h4>
            <p>{report.executive_summary}</p>
          </div>
          <div className="report-section">
            <h4>Recommendation</h4>
            <p><strong>{report.recommendation}</strong></p>
          </div>
        </>
      );
    }
    return null;
  };

  const showConnectionBanner = connectionStatus && !['connected', 'connecting', 'idle'].includes(connectionStatus);

  return (
    <div className="review-panel">
      {showConnectionBanner && (
        <div className="connection-banner error">
          실시간 스트림 연결 상태: {connectionStatus}
        </div>
      )}
      <h2>Review Status</h2>
      <p>Review ID: {reviewId}</p>
      <p>Status: <strong>{reviewStatus}</strong></p>
      {socketError && <ErrorMessage error={socketError} message="Stream Error" />}

      {renderReport()}
    </div>
  );
};

export default ReviewPanel;
