import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import LoadingSpinner from '../common/LoadingSpinner';
import ErrorMessage from '../common/ErrorMessage';

const fetchSettings = async () => {
  const { data } = await axios.get('/api/admin/settings');
  return data;
};

const updateSettings = async (settings) => {
  await axios.put('/api/admin/settings', settings);
};

const SettingsForm = () => {
  const queryClient = useQueryClient();
  const { data: settings, error, isLoading } = useQuery({
    queryKey: ['adminSettings'],
    queryFn: fetchSettings,
  });

  const mutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminSettings'] });
      alert('Settings updated successfully!');
    },
    onError: (err) => {
      alert(`Failed to update settings: ${err.response?.data?.detail || err.message}`);
    }
  });

  const handleSubmit = (event) => {
    event.preventDefault();
    const formData = new FormData(event.target);
    const newSettings = {
      FORCE_DEFAULT_PROVIDER: formData.get('FORCE_DEFAULT_PROVIDER') === 'on',
      AUTH_OPTIONAL: formData.get('AUTH_OPTIONAL') === 'on',
      METRICS_ENABLED: formData.get('METRICS_ENABLED') === 'on',
      DAILY_COST_LIMIT_USD: parseFloat(formData.get('DAILY_COST_LIMIT_USD')),
      REVIEW_COST_LIMIT_USD: parseFloat(formData.get('REVIEW_COST_LIMIT_USD')),
      MAX_PARALLEL_REVIEWS: parseInt(formData.get('MAX_PARALLEL_REVIEWS'), 10),
    };
    mutation.mutate(newSettings);
  };

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorMessage error={error} message="Failed to load system settings." />;

  return (
    <div className="settings-form">
      <h3>System Settings & Guardrails</h3>
      <form onSubmit={handleSubmit}>
        <div className="setting-card">
          <label><input type="checkbox" name="FORCE_DEFAULT_PROVIDER" defaultChecked={settings.FORCE_DEFAULT_PROVIDER} /> Force Default Provider</label>
          <label><input type="checkbox" name="AUTH_OPTIONAL" defaultChecked={settings.AUTH_OPTIONAL} /> Auth Optional</label>
          <label><input type="checkbox" name="METRICS_ENABLED" defaultChecked={settings.METRICS_ENABLED} /> Metrics Enabled</label>
        </div>
        <div className="setting-card">
          <label>Daily Cost Limit ($): <input name="DAILY_COST_LIMIT_USD" type="number" step="0.01" defaultValue={settings.DAILY_COST_LIMIT_USD} /></label>
          <label>Review Cost Limit ($): <input name="REVIEW_COST_LIMIT_USD" type="number" step="0.01" defaultValue={settings.REVIEW_COST_LIMIT_USD} /></label>
          <label>Max Parallel Reviews: <input name="MAX_PARALLEL_REVIEWS" type="number" defaultValue={settings.MAX_PARALLEL_REVIEWS} /></label>
        </div>
        <button type="submit" disabled={mutation.isLoading}>
          {mutation.isLoading ? 'Saving...' : 'Save All Settings'}
        </button>
      </form>
    </div>
  );
};

export default SettingsForm;
