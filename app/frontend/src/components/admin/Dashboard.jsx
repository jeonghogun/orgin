import React from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { Line, Bar } from 'react-chartjs-2';
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, BarElement, Title, Tooltip, Legend } from 'chart.js';
import LoadingSpinner from '../common/LoadingSpinner';
import ErrorMessage from '../common/ErrorMessage';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Title, Tooltip, Legend);

const fetchDashboardData = async () => {
  const { data } = await axios.get('/api/admin/dashboard');
  return data;
};

const Dashboard = () => {
  const { data, error, isLoading } = useQuery({
    queryKey: ['adminDashboard'],
    queryFn: fetchDashboardData,
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorMessage error={error} message="Failed to load dashboard data." />;

  const costData = {
    labels: ['Cost'],
    datasets: [
      {
        label: 'Cost Today (USD)',
        data: [data.cost_estimate_usd_today],
        backgroundColor: 'rgba(255, 99, 132, 0.5)',
      },
      {
        label: 'Budget (USD)',
        data: [data.budget_today_usd],
        backgroundColor: 'rgba(54, 162, 235, 0.5)',
      },
    ],
  };

  return (
    <div className="admin-dashboard">
      <h3>Today's Snapshot ({data.date})</h3>
      <div className="kpi-grid">
        <div className="kpi-card"><h4>Reviews Today</h4><p>{data.reviews_today}</p></div>
        <div className="kpi-card"><h4>Success Rate</h4><p>{(data.success_rate * 100).toFixed(1)}%</p></div>
        <div className="kpi-card"><h4>P95 Latency</h4><p>{data.latency_p95_ms} ms</p></div>
        <div className="kpi-card"><h4>Total Tokens</h4><p>{data.tokens_total_today}</p></div>
      </div>
      <div className="chart-container" style={{maxWidth: '600px', margin: 'auto'}}>
        <h4>Cost vs. Budget</h4>
        <Bar data={costData} />
      </div>
      {data.provider_alerts && data.provider_alerts.length > 0 && (
        <div className="alerts-section">
          <h4>Active Alerts</h4>
          <ul>
            {data.provider_alerts.map(alert => (
              <li key={alert.provider} className="error">
                High failure rate for <strong>{alert.provider}</strong>: {(alert.failure_rate * 100).toFixed(1)}%
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
