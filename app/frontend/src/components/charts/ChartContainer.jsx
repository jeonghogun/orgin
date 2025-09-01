import React from 'react';
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';

const ChartContainer = ({ 
  type = 'line',
  data = [],
  title = '',
  xAxisDataKey = 'name',
  yAxisDataKey = 'value',
  colors = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444'],
  height = 300,
  showGrid = true,
  showLegend = true,
  showTooltip = true,
  className = ''
}) => {
  const renderChart = () => {
    const commonProps = {
      data,
      margin: { top: 5, right: 30, left: 20, bottom: 5 }
    };

    switch (type) {
      case 'line':
        return (
          <LineChart {...commonProps}>
            {showGrid && <CartesianGrid strokeDasharray="3 3" stroke="#404040" />}
            <XAxis 
              dataKey={xAxisDataKey} 
              stroke="#a0a0a0"
              fontSize={12}
            />
            <YAxis 
              stroke="#a0a0a0"
              fontSize={12}
            />
            {showTooltip && <Tooltip 
              contentStyle={{
                backgroundColor: '#1a1a1a',
                border: '1px solid #404040',
                borderRadius: '8px',
                color: '#ffffff'
              }}
            />}
            {showLegend && <Legend />}
            {Array.isArray(yAxisDataKey) ? 
              yAxisDataKey.map((key, index) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={colors[index % colors.length]}
                  strokeWidth={2}
                  dot={{ fill: colors[index % colors.length], strokeWidth: 2, r: 4 }}
                  activeDot={{ r: 6, stroke: colors[index % colors.length], strokeWidth: 2 }}
                />
              )) :
              <Line
                type="monotone"
                dataKey={yAxisDataKey}
                stroke={colors[0]}
                strokeWidth={2}
                dot={{ fill: colors[0], strokeWidth: 2, r: 4 }}
                activeDot={{ r: 6, stroke: colors[0], strokeWidth: 2 }}
              />
            }
          </LineChart>
        );

      case 'area':
        return (
          <AreaChart {...commonProps}>
            {showGrid && <CartesianGrid strokeDasharray="3 3" stroke="#404040" />}
            <XAxis 
              dataKey={xAxisDataKey} 
              stroke="#a0a0a0"
              fontSize={12}
            />
            <YAxis 
              stroke="#a0a0a0"
              fontSize={12}
            />
            {showTooltip && <Tooltip 
              contentStyle={{
                backgroundColor: '#1a1a1a',
                border: '1px solid #404040',
                borderRadius: '8px',
                color: '#ffffff'
              }}
            />}
            {showLegend && <Legend />}
            {Array.isArray(yAxisDataKey) ? 
              yAxisDataKey.map((key, index) => (
                <Area
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={colors[index % colors.length]}
                  fill={colors[index % colors.length]}
                  fillOpacity={0.3}
                  strokeWidth={2}
                />
              )) :
              <Area
                type="monotone"
                dataKey={yAxisDataKey}
                stroke={colors[0]}
                fill={colors[0]}
                fillOpacity={0.3}
                strokeWidth={2}
              />
            }
          </AreaChart>
        );

      case 'bar':
        return (
          <BarChart {...commonProps}>
            {showGrid && <CartesianGrid strokeDasharray="3 3" stroke="#404040" />}
            <XAxis 
              dataKey={xAxisDataKey} 
              stroke="#a0a0a0"
              fontSize={12}
            />
            <YAxis 
              stroke="#a0a0a0"
              fontSize={12}
            />
            {showTooltip && <Tooltip 
              contentStyle={{
                backgroundColor: '#1a1a1a',
                border: '1px solid #404040',
                borderRadius: '8px',
                color: '#ffffff'
              }}
            />}
            {showLegend && <Legend />}
            {Array.isArray(yAxisDataKey) ? 
              yAxisDataKey.map((key, index) => (
                <Bar
                  key={key}
                  dataKey={key}
                  fill={colors[index % colors.length]}
                  radius={[4, 4, 0, 0]}
                />
              )) :
              <Bar
                dataKey={yAxisDataKey}
                fill={colors[0]}
                radius={[4, 4, 0, 0]}
              />
            }
          </BarChart>
        );

      case 'pie':
        return (
          <PieChart {...commonProps}>
            {showTooltip && <Tooltip 
              contentStyle={{
                backgroundColor: '#1a1a1a',
                border: '1px solid #404040',
                borderRadius: '8px',
                color: '#ffffff'
              }}
            />}
            {showLegend && <Legend />}
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              labelLine={false}
              label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
              outerRadius={80}
              fill="#8884d8"
              dataKey={yAxisDataKey}
            >
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />
              ))}
            </Pie>
          </PieChart>
        );

      default:
        return <div>지원하지 않는 차트 타입입니다.</div>;
    }
  };

  return (
    <div className={`chart-container ${className}`}>
      {title && (
        <h3 className="chart-title">{title}</h3>
      )}
      <div className="chart-wrapper" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          {renderChart()}
        </ResponsiveContainer>
      </div>
      
      <style jsx>{`
        .chart-container {
          background: rgba(40, 40, 40, 0.6);
          border: 1px solid #404040;
          border-radius: 12px;
          padding: 1.5rem;
          transition: all 0.3s ease;
        }
        
        .chart-container:hover {
          border-color: #3b82f6;
          box-shadow: 0 4px 15px rgba(59, 130, 246, 0.1);
        }
        
        .chart-title {
          color: #ffffff;
          font-size: 1.1rem;
          font-weight: 600;
          margin-bottom: 1rem;
          text-align: center;
        }
        
        .chart-wrapper {
          position: relative;
        }
      `}</style>
    </div>
  );
};

export default ChartContainer;
