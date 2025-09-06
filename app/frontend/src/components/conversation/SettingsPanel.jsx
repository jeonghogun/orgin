import React from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { useGenerationSettings, useConversationActions } from '../../store/useConversationStore';

const SettingsPanel = () => {
  const { model, temperature, maxTokens } = useGenerationSettings();
  const { setSettings } = useConversationActions();

  const { data: availableModels = [], isLoading } = useQuery({
    queryKey: ['models'],
    queryFn: async () => {
      const { data } = await axios.get('/api/convo/models');
      return data;
    },
  });

  return (
    <div className="p-2 space-y-4 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
      <div>
        <label htmlFor="model" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Model</label>
        <select
          id="model"
          value={model}
          onChange={(e) => setSettings({ model: e.target.value })}
          className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md bg-white dark:bg-gray-700"
          disabled={isLoading}
        >
          {availableModels.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
      </div>

      <div>
        <label htmlFor="temperature" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Temperature: {temperature}</label>
        <input
          id="temperature"
          type="range"
          min="0"
          max="2"
          step="0.1"
          value={temperature}
          onChange={(e) => setSettings({ temperature: parseFloat(e.target.value) })}
          className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-gray-700"
        />
      </div>

      <div>
        <label htmlFor="maxTokens" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Max Tokens: {maxTokens}</label>
        <input
          id="maxTokens"
          type="range"
          min="256"
          max="4096"
          step="256"
          value={maxTokens}
          onChange={(e) => setSettings({ maxTokens: parseInt(e.target.value, 10) })}
          className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-gray-700"
        />
      </div>
    </div>
  );
};

export default SettingsPanel;
