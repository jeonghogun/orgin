import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import toast from 'react-hot-toast';
import LoadingSpinner from '../common/LoadingSpinner';
import ErrorMessage from '../common/ErrorMessage';

const fetchGuardrailSettings = async () => {
  const { data } = await axios.get('/api/admin/settings/guardrails');
  return data;
};

const updateGuardrailSettings = async (settings) => {
  await axios.post('/api/admin/settings/guardrails', settings);
};

const GuardrailSettings = () => {
  const queryClient = useQueryClient();
  const { data: settings, error, isLoading } = useQuery({
    queryKey: ['guardrailSettings'],
    queryFn: fetchGuardrailSettings,
  });

  const mutation = useMutation({
    mutationFn: updateGuardrailSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['guardrailSettings'] });
      toast.success('Guardrail settings updated successfully!');
    },
    onError: (err) => {
      toast.error(`Failed to update settings: ${err.response?.data?.detail || err.message}`);
    }
  });

  const handleSubmit = (event) => {
    event.preventDefault();
    const formData = new FormData(event.target);
    const newSettings = {
      per_review_token_budget: parseInt(formData.get('per_review_token_budget'), 10),
      daily_org_token_budget: parseInt(formData.get('daily_org_token_budget'), 10),
    };
    mutation.mutate(newSettings);
  };

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorMessage error={error} message="Failed to load guardrail settings." />;

  return (
    <div className="guardrail-settings">
      <h3>Cost Guardrails</h3>
      <form onSubmit={handleSubmit}>
        <div className="setting-card">
          <label>Per-Review Token Budget:
            <input
              name="per_review_token_budget"
              type="number"
              defaultValue={settings.per_review_token_budget || ''}
              placeholder="e.g., 20000"
            />
          </label>
        </div>
        <div className="setting-card">
          <label>Daily Organization Token Budget:
            <input
              name="daily_org_token_budget"
              type="number"
              defaultValue={settings.daily_org_token_budget || ''}
              placeholder="e.g., 100000"
            />
          </label>
        </div>
        <button type="submit" disabled={mutation.isLoading}>
          {mutation.isLoading ? 'Saving...' : 'Save Settings'}
        </button>
      </form>
    </div>
  );
};

export default GuardrailSettings;
