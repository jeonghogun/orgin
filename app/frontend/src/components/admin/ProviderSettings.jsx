import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import LoadingSpinner from '../common/LoadingSpinner';
import ErrorMessage from '../common/ErrorMessage';

const fetchProviderConfig = async () => {
  const { data } = await axios.get('/api/admin/config/providers');
  return data;
};

const updateProviderConfig = async (config) => {
  await axios.post('/api/admin/config/providers', config);
};

const ProviderSettings = () => {
  const queryClient = useQueryClient();
  const { data: config, error, isLoading } = useQuery({
    queryKey: ['providerConfig'],
    queryFn: fetchProviderConfig,
  });

  const mutation = useMutation({
    mutationFn: updateProviderConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providerConfig'] });
      alert('Provider settings updated successfully!');
    },
    onError: (err) => {
      alert(`Failed to update settings: ${err.response?.data?.detail || err.message}`);
    }
  });

  const handleSubmit = (event) => {
    event.preventDefault();
    const formData = new FormData(event.target);
    const updatedConfig = config.map((panelist, index) => ({
      ...panelist,
      model: formData.get(`model-${index}`),
      timeout_s: parseInt(formData.get(`timeout_s-${index}`), 10),
      max_retries: parseInt(formData.get(`max_retries-${index}`), 10),
    }));
    mutation.mutate(updatedConfig);
  };

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorMessage error={error} message="Failed to load provider configuration." />;

  return (
    <div className="provider-settings">
      <h3>AI Panelist Configuration</h3>
      <form onSubmit={handleSubmit}>
        {config.map((panelist, index) => (
          <div key={panelist.provider} className="panelist-card">
            <h4>{panelist.persona} ({panelist.provider})</h4>
            <label>Model: <input name={`model-${index}`} defaultValue={panelist.model} /></label>
            <label>Timeout (s): <input name={`timeout_s-${index}`} type="number" defaultValue={panelist.timeout_s} /></label>
            <label>Max Retries: <input name={`max_retries-${index}`} type="number" defaultValue={panelist.max_retries} /></label>
          </div>
        ))}
        <button type="submit" disabled={mutation.isLoading}>
          {mutation.isLoading ? 'Saving...' : 'Save Configuration'}
        </button>
      </form>
    </div>
  );
};

export default ProviderSettings;
