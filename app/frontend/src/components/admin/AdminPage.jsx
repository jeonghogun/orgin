import React, { useState } from 'react';
import Dashboard from './Dashboard';
import ProviderTable from './ProviderTable';
import SettingsForm from './SettingsForm';
import PersonaManager from './PersonaManager';
import ExportManager from './ExportManager';

const AdminPage = () => {
  const [activeTab, setActiveTab] = useState('dashboard');

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

  const AdminTab = ({ tabKey, title }) => (
    <button onClick={() => setActiveTab(tabKey)} className={activeTab === tabKey ? 'active' : ''}>
      {title}
    </button>
  );

  return (
    <div className="admin-page">
      <h1>Admin Portal</h1>
      <div className="admin-tabs">
        <AdminTab tabKey="dashboard" title="Dashboard" />
        <AdminTab tabKey="providers" title="Providers" />
        <AdminTab tabKey="settings" title="Settings" />
        <AdminTab tabKey="personas" title="Personas & Memory" />
        <AdminTab tabKey="export" title="Export" />
      </div>
      <div className="admin-tab-content">
        {renderTabContent()}
      </div>
    </div>
  );
};

export default AdminPage;
