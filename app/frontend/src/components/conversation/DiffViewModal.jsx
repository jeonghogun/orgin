import React, { useState, useEffect } from 'react';
import ReactDiffViewer from 'react-diff-viewer';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../../lib/apiClient';

const DiffViewModal = ({ messageId, onClose }) => {
  const [selected, setSelected] = useState({ oldId: null, newId: null });

  const { data: versions = [], isLoading } = useQuery({
    queryKey: ['versions', messageId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/api/convo/messages/${messageId}/versions`);
      return data;
    },
    onSuccess: (data) => {
      if (data.length >= 2) {
        setSelected({ oldId: data[data.length - 2].id, newId: data[data.length - 1].id });
      } else if (data.length === 1) {
        setSelected({ oldId: data[0].id, newId: data[0].id });
      }
    }
  });

  const { data: diffResult, isLoading: isLoadingDiff } = useQuery({
    queryKey: ['diff', selected.oldId, selected.newId],
    queryFn: async () => {
      if (!selected.oldId || !selected.newId) return null;
      const { data } = await apiClient.get(`/api/convo/messages/${selected.newId}/diff?against=${selected.oldId}`);
      return data;
    },
    enabled: !!selected.oldId && !!selected.newId,
  });

  const oldText = versions.find(v => v.id === selected.oldId)?.content || "";
  const newText = versions.find(v => v.id === selected.newId)?.content || "";

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-6xl h-5/6 flex flex-col">
        <div className="p-4 border-b dark:border-gray-700 flex justify-between items-center">
          <h3 className="text-lg font-semibold">Compare Versions</h3>
          <button onClick={onClose} className="p-2 rounded-full hover:bg-gray-200 dark:hover:bg-gray-700">&times;</button>
        </div>
        <div className="flex-1 overflow-hidden flex">
            <div className="w-1/4 border-r dark:border-gray-700 overflow-y-auto p-2">
                <h4 className="text-sm font-bold mb-2">Versions</h4>
                {isLoading ? <p>Loading...</p> : (
                    <ul className="space-y-1">
                        {versions.map(v => (
                            <li key={v.id} className="text-xs">
                                <label className="flex items-center space-x-2 p-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700">
                                    <input type="radio" name="oldVersion" value={v.id} checked={selected.oldId === v.id} onChange={(e) => setSelected(s => ({...s, oldId: e.target.value}))} />
                                    <input type="radio" name="newVersion" value={v.id} checked={selected.newId === v.id} onChange={(e) => setSelected(s => ({...s, newId: e.target.value}))} />
                                    <span>{new Date(v.created_at * 1000).toLocaleString()}</span>
                                </label>
                            </li>
                        ))}
                    </ul>
                )}
            </div>
            <div className="w-3/4 overflow-y-auto">
                {isLoadingDiff ? <p>Loading diff...</p> : <ReactDiffViewer oldValue={oldText} newValue={newText} splitView={true} />}
            </div>
        </div>
      </div>
    </div>
  );
};

export default DiffViewModal;
