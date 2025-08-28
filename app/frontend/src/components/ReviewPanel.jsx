import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import useReviewSocket from '../hooks/useReviewSocket';
import axios from 'axios';

const ReviewPanel = () => {
  const { reviewId } = useParams();
  // In a real app, this token would come from an auth context.
  const placeholderToken = "your-placeholder-jwt-here";
  const { status: reviewStatus, error: socketError } = useReviewSocket(reviewId, placeholderToken);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchReport = async () => {
      try {
        const response = await axios.get(`/api/reviews/${reviewId}/report`);
        setReport(response.data.data);
      } catch (err) {
        // It's expected to fail until the review is complete
        console.log('Report not ready yet.');
      }
    };

    if (reviewStatus === 'completed') {
      fetchReport();
    }
  }, [reviewStatus, reviewId]);

  if (socketError || error) {
    return <div className="error">{socketError || error}</div>;
  }

  return (
    <div className="review-panel">
      <h2>Review Status</h2>
      <p>Review ID: {reviewId}</p>
      <p>Status: <strong>{reviewStatus}</strong></p>

      {reviewStatus === 'completed' && report ? (
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
      ) : (
        <p>Waiting for review to complete...</p>
      )}
    </div>
  );
};

export default ReviewPanel;
