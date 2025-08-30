import React, { useState } from 'react';
import axios from 'axios';

const ExportManager = () => {
  const [roomId, setRoomId] = useState('');
  const [isExporting, setIsExporting] = useState(false);

  const handleExport = async (format) => {
    if (!roomId.trim()) {
      alert('Please enter a Room ID.');
      return;
    }
    setIsExporting(true);
    try {
      const response = await axios.get(`/api/rooms/${roomId}/export?format=${format}`, {
        responseType: format === 'markdown' ? 'blob' : 'json',
      });

      if (format === 'markdown') {
        const url = window.URL.createObjectURL(new Blob([response.data]));
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `export_room_${roomId}_${Date.now()}.md`);
        document.body.appendChild(link);
        link.click();
        link.remove();
      } else {
        const jsonString = JSON.stringify(response.data, null, 2);
        const blob = new Blob([jsonString], { type: 'application/json' });
        const url = window.URL.createObjectURL(blob);
        window.open(url, '_blank');
      }
    } catch (err) {
      console.error(`Failed to export as ${format}`, err);
      alert(`Failed to export as ${format}: ${err.response?.data?.detail || err.message}`);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="export-manager">
      <h3>Export Room Data</h3>
      <div className="setting-card">
        <input
          type="text"
          value={roomId}
          onChange={(e) => setRoomId(e.target.value)}
          placeholder="Enter Main or Sub Room ID to export"
        />
        <div className="export-buttons">
          <button onClick={() => handleExport('json')} disabled={isExporting}>
            {isExporting ? 'Exporting...' : 'Export JSON'}
          </button>
          <button onClick={() => handleExport('markdown')} disabled={isExporting}>
            {isExporting ? 'Exporting...' : 'Export Markdown'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ExportManager;
