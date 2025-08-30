import React from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { Line } from 'react-chartjs-2';
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend } from 'chart.js';
import LoadingSpinner from '../common/LoadingSpinner';
import ErrorMessage from '../common/ErrorMessage';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

const fetchKpiData = async () => {
  const { data } = await axios.get('/api/admin/metrics/kpi');
  return data.data;
};

const KpiDashboard = () => {
  const { data: kpiData, error, isLoading } = useQuery({
    queryKey: ['kpiData'],
    queryFn: fetchKpiData,
  });

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorMessage error={error} message="Failed to load KPI data." />;

  const chartOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'top',
      },
      title: {
        display: true,
        text: 'KPI Trends (Last 30 Days)',
      },
    },
  };

  const generateChartData = (metricName) => {
    const metric = kpiData?.[metricName];
    return {
      labels: metric?.dates || [],
      datasets: [
        {
          label: metricName.replace(/_/g, ' ').toUpperCase(),
          data: metric?.values || [],
          borderColor: 'rgb(75, 192, 192)',
          backgroundColor: 'rgba(75, 192, 192, 0.5)',
        },
      ],
    };
  };

  return (
    <div className="kpi-dashboard">
      <h3>Investor & KPI Dashboard</h3>
      <div className="charts-grid">
        <div className="chart-container">
          {kpiData?.daily_active_users && <Line options={chartOptions} data={generateChartData('daily_active_users')} />}
        </div>
        <div className="chart-container">
          {kpiData?.new_reviews_created && <Line options={chartOptions} data={generateChartData('new_reviews_created')} />}
        </div>
        <div className="chart-container">
          {kpiData?.total_token_cost && <Line options={chartOptions} data={generateChartData('total_token_cost')} />}
        </div>
        <div className="chart-container">
          {kpiData?.avg_review_cost && <Line options={chartOptions} data={generateChartData('avg_review_cost')} />}
        </div>
      </div>
    </div>
  );
};

export default KpiDashboard;
