import React from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

const fetchRooms = async () => {
  const { data } = await axios.get('/api/rooms');
  return data;
};

import LoadingSpinner from './common/LoadingSpinner';
import ErrorMessage from './common/ErrorMessage';
import EmptyState from './common/EmptyState';

const RoomList = ({ onRoomSelect }) => {
  const { data: rooms, error, isLoading } = useQuery({
    queryKey: ['rooms'],
    queryFn: fetchRooms,
  });

  const renderContent = () => {
    if (isLoading) {
      return <LoadingSpinner />;
    }

    if (error) {
      return <ErrorMessage error={error} message="Failed to fetch rooms." />;
    }

    if (!rooms || rooms.length === 0) {
      return <EmptyState message="No rooms found. Create one to get started." />;
    }

    return (
      <ul>
        {rooms.map((room) => (
          <li key={room.room_id} onClick={() => onRoomSelect(room.room_id)} className="room-item">
            {room.name} ({room.type})
          </li>
        ))}
      </ul>
    );
  };

  return (
    <div className="room-list">
      <h2>Rooms</h2>
      {renderContent()}
    </div>
  );
};

export default RoomList;
