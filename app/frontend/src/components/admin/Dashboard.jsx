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
  if (error) return <ErrorMessage error={error} message="대시보드 데이터를 불러올 수 없습니다." />;

  const costData = {
    labels: ['비용'],
    datasets: [
      {
        label: '오늘 비용 (USD)',
        data: [data.cost_estimate_usd_today],
        backgroundColor: 'rgba(255, 99, 132, 0.5)',
      },
      {
        label: '예산 (USD)',
        data: [data.budget_today_usd],
        backgroundColor: 'rgba(54, 162, 235, 0.5)',
      },
    ],
  };

  return (
    <div className="admin-dashboard">
      <h3>오늘의 스냅샷 ({data.date})</h3>
      <div className="kpi-grid">
        <div className="kpi-card"><h4>오늘 리뷰 수</h4><p>{data.reviews_today}</p></div>
        <div className="kpi-card"><h4>성공률</h4><p>{(data.success_rate * 100).toFixed(1)}%</p></div>
        <div className="kpi-card"><h4>P95 지연시간</h4><p>{data.latency_p95_ms} ms</p></div>
        <div className="kpi-card"><h4>총 토큰 수</h4><p>{data.tokens_total_today}</p></div>
      </div>
      <div className="chart-container" style={{maxWidth: '600px', margin: 'auto'}}>
        <h4>비용 vs 예산</h4>
        <Bar data={costData} />
      </div>
      {data.provider_alerts && data.provider_alerts.length > 0 && (
        <div className="alerts-section">
          <h4>활성 알림</h4>
          <ul>
            {data.provider_alerts.map(alert => (
              <li key={alert.provider} className="error">
                <strong>{alert.provider}</strong>의 높은 실패률: {(alert.failure_rate * 100).toFixed(1)}%
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
