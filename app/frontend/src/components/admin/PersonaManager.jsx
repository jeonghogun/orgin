import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import apiClient from '../../lib/apiClient';
import LoadingSpinner from '../common/LoadingSpinner';
import ErrorMessage from '../common/ErrorMessage';

const fetchPersonaJobs = async () => {
  const { data } = await apiClient.get('/api/admin/persona/jobs');
  return data.jobs;
};

const rebuildPersona = async (userId) => {
  await apiClient.post('/api/admin/persona/rebuild', { user_id: userId });
};

const PersonaManager = () => {
  const queryClient = useQueryClient();
  const [userId, setUserId] = useState('');
  const { data: jobs, error, isLoading } = useQuery({
    queryKey: ['personaJobs'],
    queryFn: fetchPersonaJobs,
    refetchInterval: 5000,
  });

  const mutation = useMutation({
    mutationFn: rebuildPersona,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['personaJobs'] });
            toast.success('Persona rebuild task enqueued!');
      setUserId('');
    },
    onError: (err) => {
            toast.error(`Failed to start rebuild: ${err.response?.data?.detail || err.message}`);
    }
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!userId.trim()) return;
    mutation.mutate(userId);
  };

  return (
    <div className="persona-manager">
      <h3>Persona & Memory Tools</h3>
      <div className="setting-card">
        <h4>Rebuild User Persona</h4>
        <form onSubmit={handleSubmit}>
          <input
            type="text"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="Enter User ID to rebuild persona"
          />
          <button type="submit" disabled={mutation.isLoading}>
            {mutation.isLoading ? 'Enqueuing...' : 'Rebuild Persona'}
          </button>
        </form>
      </div>
      <div className="setting-card">
        <h4>Recent Persona Jobs</h4>
        {isLoading && <LoadingSpinner />}
        {error && <ErrorMessage error={error} message="Could not load persona jobs." />}
        <ul>
          {jobs && jobs.length > 0 ? jobs.map(job => (
            <li key={job.id}>{job.id} - {job.status}</li>
          )) : <p>No recent jobs.</p>}
        </ul>
      </div>
    </div>
  );
};

export default PersonaManager;
