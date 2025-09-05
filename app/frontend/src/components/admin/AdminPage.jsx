import React, { useState } from 'react';
import Dashboard from './Dashboard';
import ProviderTable from './ProviderTable';
import SettingsForm from './SettingsForm';
import PersonaManager from './PersonaManager';
import ExportManager from './ExportManager';

const AdminPage = () => {
  const [activeTab, setActiveTab] = useState('dashboard');

  const tabs = [
    { key: 'dashboard', title: '대시보드', icon: '📊' },
    { key: 'providers', title: '프로바이더', icon: '🔧' },
    { key: 'settings', title: '설정', icon: '⚙️' },
    { key: 'personas', title: '페르소나 & 메모리', icon: '👤' },
    { key: 'export', title: '내보내기', icon: '📤' }
  ];

  const renderTabContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return <Dashboard />;
      case 'providers':
        return <ProviderTable />;
      case 'settings':
        return <SettingsForm />;
      case 'personas':
        return <PersonaManager />;
      case 'export':
        return <ExportManager />;
      default:
        return <Dashboard />;
    }
  };

  return (
    <div className="admin-page">
      <div className="admin-header">
        <h1>관리자 포털</h1>
        <p>시스템 설정 및 모니터링을 관리하세요</p>
      </div>

      <div className="admin-container">
        <div className="admin-sidebar">
          <nav className="admin-nav">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                className={`admin-nav-item ${activeTab === tab.key ? 'active' : ''}`}
                onClick={() => setActiveTab(tab.key)}
              >
                <span className="nav-icon">{tab.icon}</span>
                <span className="nav-title">{tab.title}</span>
              </button>
            ))}
          </nav>
        </div>

        <div className="admin-content">
          {renderTabContent()}
        </div>
      </div>

      <style jsx>{`
        .admin-page {
          min-height: 100vh;
          background: linear-gradient(135deg, #0f0f0f 0%, #1a1a1a 100%);
          padding: 2rem;
        }

        .admin-header {
          text-align: center;
          margin-bottom: 3rem;
        }

        .admin-header h1 {
          color: #ffffff;
          font-size: 2.5rem;
          font-weight: 700;
          margin-bottom: 0.5rem;
          background: linear-gradient(135deg, #3b82f6, #8b5cf6);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }

        .admin-header p {
          color: #a0a0a0;
          font-size: 1.1rem;
        }

        .admin-container {
          display: flex;
          gap: 2rem;
          max-width: 1400px;
          margin: 0 auto;
          min-height: calc(100vh - 200px);
        }

        .admin-sidebar {
          width: 280px;
          flex-shrink: 0;
        }

        .admin-nav {
          background: rgba(40, 40, 40, 0.6);
          border: 1px solid #404040;
          border-radius: 16px;
          padding: 1rem;
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }

        .admin-nav-item {
          display: flex;
          align-items: center;
          gap: 1rem;
          padding: 1rem 1.25rem;
          background: transparent;
          border: none;
          border-radius: 12px;
          color: #a0a0a0;
          font-size: 1rem;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.3s ease;
          text-align: left;
          position: relative;
          overflow: hidden;
        }

        .admin-nav-item::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: linear-gradient(135deg, #3b82f6, #8b5cf6);
          opacity: 0;
          transition: opacity 0.3s ease;
          z-index: -1;
        }

        .admin-nav-item:hover {
          color: #ffffff;
          transform: translateX(4px);
        }

        .admin-nav-item:hover::before {
          opacity: 0.1;
        }

        .admin-nav-item.active {
          background: linear-gradient(135deg, rgba(59, 130, 246, 0.15), rgba(139, 92, 246, 0.15));
          color: #3b82f6;
          border: 1px solid #3b82f6;
        }

        .admin-nav-item.active::before {
          opacity: 0;
        }

        .nav-icon {
          font-size: 1.25rem;
          width: 24px;
          text-align: center;
        }

        .nav-title {
          font-weight: 600;
        }

        .admin-content {
          flex: 1;
          background: rgba(40, 40, 40, 0.6);
          border: 1px solid #404040;
          border-radius: 16px;
          padding: 2rem;
          overflow-y: auto;
        }

        @media (max-width: 1024px) {
          .admin-container {
            flex-direction: column;
          }

          .admin-sidebar {
            width: 100%;
          }

          .admin-nav {
            flex-direction: row;
            overflow-x: auto;
            padding: 1rem;
          }

          .admin-nav-item {
            flex-shrink: 0;
            min-width: 140px;
            justify-content: center;
          }

          .nav-title {
            display: none;
          }

          .nav-icon {
            font-size: 1.5rem;
          }
        }

        @media (max-width: 768px) {
          .admin-page {
            padding: 1rem;
          }

          .admin-header h1 {
            font-size: 2rem;
          }

          .admin-content {
            padding: 1rem;
          }
        }
      `}</style>
    </div>
  );
};

export default AdminPage;
