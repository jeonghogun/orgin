import React, { useState, useEffect } from 'react';
import axios from 'axios';
import LoadingSpinner from './common/LoadingSpinner';
import ErrorMessage from './common/ErrorMessage';
import EmptyState from './common/EmptyState';

const MetricsDashboard = () => {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchMetricsSummary();
  }, []);

  const fetchMetricsSummary = async () => {
    try {
      setLoading(true);
      const { data } = await axios.get('/api/metrics/summary');
      setSummary(data);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorMessage error={error} message="메트릭 대시보드를 불러올 수 없습니다." />;
  if (!summary) return <EmptyState message="아직 메트릭 데이터가 없습니다." />;

  const formatDuration = (seconds) => {
    if (seconds < 60) return `${seconds.toFixed(1)}초`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}분 ${remainingSeconds.toFixed(0)}초`;
  };

  const formatTokens = (tokens) => {
    if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}K`;
    return tokens.toFixed(0);
  };

  return (
    <div className="metrics-dashboard">
      <div className="metrics-header">
        <h1>메트릭 대시보드</h1>
        <p>AI 검토 시스템의 성능 및 사용 현황을 확인하세요</p>
      </div>

      <div className="metrics-grid">
        {/* 전체 통계 카드 */}
        <div className="metric-card primary">
          <div className="metric-icon">📊</div>
          <div className="metric-content">
            <h3>전체 검토</h3>
            <div className="metric-value">{summary.total_reviews.toLocaleString()}</div>
            <p>총 완료된 검토 수</p>
          </div>
        </div>

        {/* 평균 지속시간 */}
        <div className="metric-card">
          <div className="metric-icon">⏱️</div>
          <div className="metric-content">
            <h3>평균 지속시간</h3>
            <div className="metric-value">{formatDuration(summary.avg_duration)}</div>
            <p>검토당 평균 소요 시간</p>
          </div>
        </div>

        {/* 중간값 지속시간 */}
        <div className="metric-card">
          <div className="metric-icon">📈</div>
          <div className="metric-content">
            <h3>중간값 지속시간</h3>
            <div className="metric-value">{formatDuration(summary.median_duration)}</div>
            <p>검토 지속시간 중간값</p>
          </div>
        </div>

        {/* P95 지속시간 */}
        <div className="metric-card">
          <div className="metric-icon">🎯</div>
          <div className="metric-content">
            <h3>P95 지속시간</h3>
            <div className="metric-value">{formatDuration(summary.p95_duration)}</div>
            <p>95% 검토가 이 시간 내 완료</p>
          </div>
        </div>

        {/* 평균 토큰 사용량 */}
        <div className="metric-card">
          <div className="metric-icon">🧠</div>
          <div className="metric-content">
            <h3>평균 토큰</h3>
            <div className="metric-value">{formatTokens(summary.avg_tokens)}</div>
            <p>검토당 평균 토큰 사용량</p>
          </div>
        </div>

        {/* 중간값 토큰 사용량 */}
        <div className="metric-card">
          <div className="metric-icon">📊</div>
          <div className="metric-content">
            <h3>중간값 토큰</h3>
            <div className="metric-value">{formatTokens(summary.median_tokens)}</div>
            <p>토큰 사용량 중간값</p>
          </div>
        </div>

        {/* P95 토큰 사용량 */}
        <div className="metric-card">
          <div className="metric-icon">⚡</div>
          <div className="metric-content">
            <h3>P95 토큰</h3>
            <div className="metric-value">{formatTokens(summary.p95_tokens)}</div>
            <p>95% 검토가 이 토큰 수 이하</p>
          </div>
        </div>
      </div>

      {/* 프로바이더별 요약 */}
      {summary.provider_summary && Object.keys(summary.provider_summary).length > 0 && (
        <div className="provider-summary">
          <h2>프로바이더별 사용 현황</h2>
          <div className="provider-grid">
            {Object.entries(summary.provider_summary).map(([provider, stats]) => (
              <div key={provider} className="provider-card">
                <div className="provider-header">
                  <h3>{provider.toUpperCase()}</h3>
                  <span className="provider-count">{stats.count}회</span>
                </div>
                <div className="provider-stats">
                  <div className="provider-stat">
                    <span>평균 지속시간:</span>
                    <span>{formatDuration(stats.avg_duration)}</span>
                  </div>
                  <div className="provider-stat">
                    <span>평균 토큰:</span>
                    <span>{formatTokens(stats.avg_tokens)}</span>
                  </div>
                  <div className="provider-stat">
                    <span>성공률:</span>
                    <span>{(stats.success_rate * 100).toFixed(1)}%</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <style jsx>{`
        .metrics-dashboard {
          padding: 2rem;
          max-width: 1400px;
          margin: 0 auto;
        }

        .metrics-header {
          text-align: center;
          margin-bottom: 3rem;
        }

        .metrics-header h1 {
          color: #ffffff;
          font-size: 2.5rem;
          font-weight: 700;
          margin-bottom: 0.5rem;
          background: linear-gradient(135deg, #3b82f6, #8b5cf6);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }

        .metrics-header p {
          color: #a0a0a0;
          font-size: 1.1rem;
        }

        .metrics-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          gap: 1.5rem;
          margin-bottom: 3rem;
        }

        .metric-card {
          background: rgba(40, 40, 40, 0.6);
          border: 1px solid #404040;
          border-radius: 16px;
          padding: 1.5rem;
          transition: all 0.3s ease;
          position: relative;
          overflow: hidden;
        }

        .metric-card::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 3px;
          background: linear-gradient(90deg, #3b82f6, #8b5cf6);
          transform: scaleX(0);
          transition: transform 0.3s ease;
        }

        .metric-card:hover {
          background: rgba(59, 130, 246, 0.1);
          border-color: #3b82f6;
          transform: translateY(-4px);
          box-shadow: 0 12px 30px rgba(59, 130, 246, 0.2);
        }

        .metric-card:hover::before {
          transform: scaleX(1);
        }

        .metric-card.primary {
          background: linear-gradient(135deg, rgba(59, 130, 246, 0.1), rgba(139, 92, 246, 0.1));
          border-color: #3b82f6;
        }

        .metric-card.primary::before {
          transform: scaleX(1);
        }

        .metric-icon {
          font-size: 2rem;
          margin-bottom: 1rem;
        }

        .metric-content h3 {
          color: #a0a0a0;
          font-size: 0.9rem;
          font-weight: 500;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          margin-bottom: 0.5rem;
        }

        .metric-value {
          color: #ffffff;
          font-size: 2rem;
          font-weight: 700;
          margin-bottom: 0.5rem;
        }

        .metric-content p {
          color: #808080;
          font-size: 0.875rem;
          margin: 0;
        }

        .provider-summary {
          margin-top: 3rem;
        }

        .provider-summary h2 {
          color: #ffffff;
          font-size: 1.5rem;
          font-weight: 600;
          margin-bottom: 1.5rem;
          text-align: center;
        }

        .provider-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
          gap: 1.5rem;
        }

        .provider-card {
          background: rgba(40, 40, 40, 0.6);
          border: 1px solid #404040;
          border-radius: 12px;
          padding: 1.5rem;
          transition: all 0.3s ease;
        }

        .provider-card:hover {
          background: rgba(59, 130, 246, 0.1);
          border-color: #3b82f6;
          transform: translateY(-2px);
        }

        .provider-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1rem;
          padding-bottom: 0.75rem;
          border-bottom: 1px solid #404040;
        }

        .provider-header h3 {
          color: #ffffff;
          font-size: 1.1rem;
          font-weight: 600;
          margin: 0;
        }

        .provider-count {
          background: linear-gradient(135deg, #3b82f6, #8b5cf6);
          color: #ffffff;
          padding: 0.25rem 0.75rem;
          border-radius: 20px;
          font-size: 0.875rem;
          font-weight: 600;
        }

        .provider-stats {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }

        .provider-stat {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .provider-stat span:first-child {
          color: #a0a0a0;
          font-size: 0.875rem;
        }

        .provider-stat span:last-child {
          color: #ffffff;
          font-weight: 600;
        }

        @media (max-width: 768px) {
          .metrics-dashboard {
            padding: 1rem;
          }

          .metrics-header h1 {
            font-size: 2rem;
          }

          .metrics-grid {
            grid-template-columns: 1fr;
            gap: 1rem;
          }

          .provider-grid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </div>
  );
};

export default MetricsDashboard;
