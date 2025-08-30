import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import useReviewSocket from '../hooks/useReviewSocket';
import axios from 'axios';

import { useQuery } from '@tanstack/react-query';
import LoadingSpinner from './common/LoadingSpinner';
import ErrorMessage from './common/ErrorMessage';

const fetchReport = async (reviewId) => {
  const { data } = await axios.get(`/api/reviews/${reviewId}/report`);
  return data.data;
};

const ReviewPanel = () => {
  const { reviewId } = useParams();
  const placeholderToken = "your-placeholder-jwt-here";
  const { status: reviewStatus, error: socketError, connectionStatus } = useReviewSocket(reviewId, placeholderToken);

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

  return (
    <div className="review-panel">
      {connectionStatus !== 'connected' && (
        <div className="connection-banner error">
          WebSocket disconnected. Attempting to reconnect... ({connectionStatus})
        </div>
      )}
      <h2>Review Status</h2>
      <p>Review ID: {reviewId}</p>
      <p>Status: <strong>{reviewStatus}</strong></p>
      {socketError && <ErrorMessage error={socketError} message="WebSocket Error" />}

      {renderReport()}
    </div>
  );
};

export default ReviewPanel;
