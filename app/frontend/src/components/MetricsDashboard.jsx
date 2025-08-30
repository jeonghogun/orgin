import React from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

const fetchMetricsSummary = async () => {
  const { data } = await axios.get('/api/metrics/summary');
  return data.data;
};

import LoadingSpinner from './common/LoadingSpinner';
import ErrorMessage from './common/ErrorMessage';
import EmptyState from './common/EmptyState';

const MetricsDashboard = () => {
  const { data: summary, error, isLoading } = useQuery({
    queryKey: ['metricsSummary'],
    queryFn: fetchMetricsSummary,
    refetchInterval: 10000,
  });

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorMessage error={error} message="Could not load metrics dashboard." />;
  if (!summary) return <EmptyState message="No metrics data available yet." />;

  return (
    <div className="metrics-dashboard">
      <h2>Overall Summary</h2>
      <div className="metrics-grid">
        <div className="metric-card">
          <h4>Total Reviews</h4>
          <p>{summary.total_reviews}</p>
        </div>
        <div className="metric-card">
          <h4>Avg. Duration (s)</h4>
          <p>{summary.avg_duration.toFixed(2)}</p>
        </div>
        <div className="metric-card">
          <h4>P95 Duration (s)</h4>
          <p>{summary.p95_duration.toFixed(2)}</p>
        </div>
        <div className="metric-card">
          <h4>Avg. Tokens</h4>
          <p>{summary.avg_tokens.toFixed(0)}</p>
        </div>
        <div className="metric-card">
          <h4>P95 Tokens</h4>
          <p>{summary.p95_tokens.toFixed(0)}</p>
        </div>
      </div>

      <h2>Provider Performance</h2>
      <table className="provider-metrics-table">
        <thead>
          <tr>
            <th>Provider</th>
            <th>Total Calls</th>
            <th>Success Rate</th>
            <th>Avg. Tokens</th>
            <th>Avg. Duration (s)</th>
          </tr>
        </thead>
        <tbody>
          {summary.provider_summary && Object.entries(summary.provider_summary).map(([provider, stats]) => (
            <tr key={provider}>
              <td>{provider}</td>
              <td>{stats.total_calls}</td>
              <td>{(stats.success_rate * 100).toFixed(1)}%</td>
              <td>{stats.avg_tokens.toFixed(0)}</td>
              <td>{stats.avg_duration.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default MetricsDashboard;
