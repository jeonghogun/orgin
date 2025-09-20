import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

const fetchRooms = async () => {
  const { data } = await axios.get('/api/rooms');
  if (!Array.isArray(data)) {
    console.warn('useRoomsQuery: received non-array payload for rooms', data);
    return [];
  }
  return data;
};

const DEFAULT_QUERY_OPTIONS = {
  queryKey: ['rooms'],
  queryFn: fetchRooms,
  staleTime: 5 * 60 * 1000,
  retry: 1,
};

const useRoomsQuery = (options = {}) => {
  return useQuery({
    ...DEFAULT_QUERY_OPTIONS,
    ...options,
  });
};

export default useRoomsQuery;
