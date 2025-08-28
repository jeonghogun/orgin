import React from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

const fetchRooms = async () => {
  const { data } = await axios.get('/api/rooms');
  return data;
};

const RoomList = ({ onRoomSelect }) => {
  const { data: rooms, error, isLoading } = useQuery({
    queryKey: ['rooms'],
    queryFn: fetchRooms,
  });

  if (isLoading) {
    return <div>Loading rooms...</div>;
  }

  if (error) {
    return <div className="error">Failed to fetch rooms.</div>;
  }

  return (
    <div className="room-list">
      <h2>Rooms</h2>
      <ul>
        {rooms && rooms.length > 0 ? (
          rooms.map((room) => (
            <li key={room.room_id} onClick={() => onRoomSelect(room.room_id)} className="room-item">
              {room.name} ({room.type})
            </li>
          ))
        ) : (
          <p>No rooms found.</p>
        )}
      </ul>
    </div>
  );
};

export default RoomList;
