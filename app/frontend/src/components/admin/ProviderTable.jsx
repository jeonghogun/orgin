import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import apiClient from '../../lib/apiClient';
import LoadingSpinner from '../common/LoadingSpinner';
import ErrorMessage from '../common/ErrorMessage';

const fetchProviders = async () => {
  const { data } = await apiClient.get('/api/admin/providers');
  return data;
};

const updateProvider = async ({ name, config }) => {
  await apiClient.put(`/api/admin/providers/${name}`, config);
};

const ProviderTable = () => {
  const queryClient = useQueryClient();
  const { data: providers, error, isLoading } = useQuery({
    queryKey: ['adminProviders'],
    queryFn: fetchProviders,
  });

  const mutation = useMutation({
    mutationFn: updateProvider,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminProviders'] });
      toast.success('Provider updated successfully!');
    },
    onError: (err) => {
      toast.error(`Failed to update provider: ${err.response?.data?.detail || err.message}`);
    }
  });

  // Basic inline form for editing, a modal would be better in a real app
  const handleEdit = (provider) => {
    const newModel = prompt("Enter new model:", provider.model);
    if (newModel) {
      const config = { ...provider, model: newModel };
      delete config.name;
      delete config.stats_24h;
      mutation.mutate({ name: provider.name, config });
    }
  };

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorMessage error={error} message="Failed to load provider data." />;

  return (
    <div className="provider-table">
      <h3>Provider Configuration & Stats (Last 24h)</h3>
      <table>
        <thead>
          <tr>
            <th>Provider</th>
            <th>Enabled</th>
            <th>Model</th>
            <th>Success/Fail</th>
            <th>P95 Latency (ms)</th>
            <th>P50 Cost (USD)</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {providers && providers.map(p => (
            <tr key={p.name}>
              <td>{p.name}</td>
              <td>{p.enabled ? '✅' : '❌'}</td>
              <td>{p.model}</td>
              <td>{p.stats_24h.success} / {p.stats_24h.fail}</td>
              <td>{p.stats_24h.latency_p95_ms}</td>
              <td>${p.stats_24h.cost_per_review_p50_usd.toFixed(4)}</td>
              <td><button onClick={() => handleEdit(p)}>Edit</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default ProviderTable;
