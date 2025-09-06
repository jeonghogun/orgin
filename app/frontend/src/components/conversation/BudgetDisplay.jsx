import React from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

const BudgetDisplay = () => {
  const { data, error, isLoading } = useQuery({
    queryKey: ['dailyUsage'],
    queryFn: async () => {
      const { data } = await axios.get('/api/convo/usage/today');
      return data;
    },
    refetchInterval: 30000, // Refetch every 30 seconds
  });

  if (isLoading || error || !data || !data.budget) {
    return null; // Don't render if there's no budget set or on error
  }

  const percentage = (data.usage / data.budget) * 100;

  let bgColor = 'bg-green-500';
  if (percentage > 90) {
    bgColor = 'bg-red-500';
  } else if (percentage > 70) {
    bgColor = 'bg-yellow-500';
  }

  return (
    <div className="p-2 bg-gray-100 dark:bg-gray-900 rounded-lg">
      <div className="flex justify-between items-center text-xs mb-1 text-gray-600 dark:text-gray-400">
        <span>Daily Usage</span>
        <span>{data.usage} / {data.budget} Tokens</span>
      </div>
      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
        <div className={`${bgColor} h-2 rounded-full`} style={{ width: `${Math.min(percentage, 100)}%` }}></div>
      </div>
    </div>
  );
};

export default BudgetDisplay;
