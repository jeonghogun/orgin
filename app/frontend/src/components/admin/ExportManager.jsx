import React, { useState, useEffect, useCallback } from 'react';
import toast from 'react-hot-toast';
import apiClient, { resolveApiUrl } from '../../lib/apiClient';

const POLLING_INTERVAL = 2000; // 2 seconds

const ExportManager = () => {
  const [threadId, setThreadId] = useState('');
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);

  const pollJobStatus = useCallback(async (jobId) => {
    try {
      const { data } = await apiClient.get(`/api/export/jobs/${jobId}`);
      if (data.status === 'done' || data.status === 'error') {
        setJob(data);
      } else {
        // If still processing, poll again
        setTimeout(() => pollJobStatus(jobId), POLLING_INTERVAL);
        setJob(data); // Update status for UI
      }
    } catch (err) {
      console.error('Failed to poll job status', err);
      setError('Failed to get export status.');
      setJob(null);
    }
  }, []);

// ... (rest of the imports)

// ... (inside the component)
  const handleExport = async (format) => {
    if (!threadId.trim()) {
      toast.error('Please enter a Thread ID.');
      return;
    }
    setError(null);
    setJob({ status: 'starting' });

    try {
      // Note the API path change to /api/threads/...
      const response = await apiClient.post(`/api/threads/${threadId.trim()}/export/jobs?format=${format}`);
      const { jobId } = response.data;
      
      if (jobId) {
        setJob({ id: jobId, status: 'queued' });
        // Start polling for status
        setTimeout(() => pollJobStatus(jobId), POLLING_INTERVAL);
      } else {
        throw new Error("jobId not returned from server");
      }
    } catch (err) {
      console.error(`Failed to start export as ${format}`, err);
      const errorMsg = err.response?.data?.detail || err.message;
      setError(`Failed to start export: ${errorMsg}`);
      setJob(null);
    }
  };

  const isExporting = job && (job.status === 'starting' || job.status === 'queued' || job.status === 'processing');

  return (
    <div className="export-manager p-4 border rounded-lg bg-gray-50 dark:bg-gray-800">
      <h3 className="text-lg font-semibold mb-2">Export Thread Data</h3>
      <div className="space-y-4">
        <input
          type="text"
          value={threadId}
          onChange={(e) => setThreadId(e.target.value)}
          placeholder="Enter Thread ID to export"
          className="w-full p-2 border rounded-md dark:bg-gray-700 dark:border-gray-600"
          disabled={isExporting}
        />
        <div className="flex items-center space-x-2">
          <button onClick={() => handleExport('zip')} disabled={isExporting} className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:bg-gray-400">
            {isExporting ? 'Exporting...' : 'Export as ZIP'}
          </button>
        </div>
        
        {error && (
          <div className="p-3 bg-red-100 text-red-800 rounded-md">
            <strong>Error:</strong> {error}
          </div>
        )}

        {job && (
          <div className="p-3 bg-gray-100 dark:bg-gray-700 rounded-md space-y-2">
            <p><strong>Status:</strong> <span className="font-mono px-2 py-1 bg-gray-200 dark:bg-gray-600 rounded-md">{job.status}</span></p>
            {job.id && <p><strong>Job ID:</strong> {job.id}</p>}
            
            {job.status === 'done' && job.file_url && (
              <a
                href={resolveApiUrl(`/api/export/jobs/${job.id}/download`)}
                className="inline-block px-4 py-2 bg-green-500 text-white rounded-md hover:bg-green-600"
                download
              >
                Download File
              </a>
            )}
            
            {job.status === 'error' && job.error_message && (
              <p className="text-red-500"><strong>Details:</strong> {job.error_message}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default ExportManager;
