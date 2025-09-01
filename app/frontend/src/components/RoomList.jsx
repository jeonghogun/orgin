import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';

import LoadingSpinner from './common/LoadingSpinner';
import ErrorMessage from './common/ErrorMessage';
import EmptyState from './common/EmptyState';

const fetchRooms = async () => {
  const { data } = await axios.get('/api/rooms');
  return data;
};

const buildRoomHierarchy = (rooms) => {
  if (!rooms) return [];
  const roomMap = new Map();
  rooms.forEach(room => {
    room.children = [];
    roomMap.set(room.room_id, room);
  });

  const hierarchy = [];
  rooms.forEach(room => {
    if (room.parent_id) {
      const parent = roomMap.get(room.parent_id);
      if (parent) {
        parent.children.push(room);
      } else {
        // In case parent is not in the list, treat it as a root
        hierarchy.push(room);
      }
    } else {
      hierarchy.push(room);
    }
  });

  return hierarchy;
};

const updateRoomName = async ({ roomId, name }) => {
  const { data } = await axios.patch(`/api/rooms/${roomId}`, { name });
  return data;
};

const RoomItem = ({ room, onRoomSelect, level, editingRoomId, setEditingRoomId, setEditingName, handleUpdateName }) => {
  const [isHovered, setIsHovered] = useState(false);

  const isEditing = editingRoomId === room.room_id;

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      handleUpdateName();
    } else if (e.key === 'Escape') {
      setEditingRoomId(null);
    }
  };

  return (
    <>
      <li
        className="room-item-li"
        style={{ paddingLeft: `${level * 20}px` }}
        onClick={() => !isEditing && onRoomSelect(room.room_id)}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        {isEditing ? (
          <input
            type="text"
            className="room-item-input"
            defaultValue={room.name}
            onChange={(e) => setEditingName(e.target.value)}
            onBlur={handleUpdateName}
            onKeyDown={handleKeyDown}
            autoFocus
          />
        ) : (
          <>
            <span>{room.name}</span>
            {isHovered && (
              <button
                className="room-item-edit-button"
                onClick={(e) => {
                  e.stopPropagation(); // Prevent li's onClick from firing
                  setEditingRoomId(room.room_id);
                  setEditingName(room.name);
                }}
              >
                ✏️
              </button>
            )}
          </>
        )}
      </li>
      {room.children && room.children.length > 0 && (
        <li>
          <ul className="room-item-children-ul">
            {room.children.map(child => (
              <RoomItem
                key={child.room_id}
                room={child}
                onRoomSelect={onRoomSelect}
                level={level + 1}
                editingRoomId={editingRoomId}
                setEditingRoomId={setEditingRoomId}
                setEditingName={setEditingName}
                handleUpdateName={handleUpdateName}
              />
            ))}
          </ul>
        </li>
      )}
    </>
  );
};


const RoomList = ({ onRoomSelect }) => {
  const queryClient = useQueryClient();
  const [editingRoomId, setEditingRoomId] = useState(null);
  const [editingName, setEditingName] = useState('');

  const { data: rooms, error, isLoading } = useQuery({
    queryKey: ['rooms'],
    queryFn: fetchRooms,
  });

  const mutation = useMutation({
    mutationFn: updateRoomName,
    onSuccess: () => {
      queryClient.invalidateQueries(['rooms']);
      setEditingRoomId(null);
    },
    onError: (err) => {
      console.error("Failed to update room name:", err);
      // Optionally, show an error message to the user
      setEditingRoomId(null);
    }
  });

  const handleUpdateName = () => {
    if (editingRoomId && editingName) {
      mutation.mutate({ roomId: editingRoomId, name: editingName });
    } else {
      setEditingRoomId(null); // Cancel if name is empty or something went wrong
    }
  };

  const renderContent = () => {
    if (isLoading) {
      return <LoadingSpinner />;
    }

    if (error) {
      return <ErrorMessage error={error} message="Failed to fetch rooms." />;
    }

    const hierarchicalRooms = buildRoomHierarchy(rooms);

    if (hierarchicalRooms.length === 0) {
      return <EmptyState message="No rooms found. Create one to get started." />;
    }

    return (
      <ul className="room-list-ul">
        {hierarchicalRooms.map((room) => (
          <RoomItem
            key={room.room_id}
            room={room}
            onRoomSelect={onRoomSelect}
            level={0}
            editingRoomId={editingRoomId}
            setEditingRoomId={setEditingRoomId}
            setEditingName={setEditingName}
            handleUpdateName={handleUpdateName}
          />
        ))}
      </ul>
    );
  };

  return (
    <div className="room-list-container">
      <h2 className="room-list-header">Rooms</h2>
      {renderContent()}
    </div>
  );
};

export default RoomList;
