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
      <div
        className="room-item"
        style={{ paddingLeft: `${level * 20}px` }}
        onClick={() => !isEditing && onRoomSelect(room.room_id)}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M21 15C21 15.5304 20.7893 16.0391 20.4142 16.4142C20.0391 16.7893 19.5304 17 19 17H7L3 21V5C3 4.46957 3.21071 3.96086 3.58579 3.58579C3.96086 3.21071 4.46957 3 5 3H19C19.5304 3 20.0391 3.21071 20.4142 3.58579C20.7893 3.96086 21 4.46957 21 5V15Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
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
            <span className="room-name">{room.name}</span>
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
      </div>
      {room.children && room.children.length > 0 && (
        <div>
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
        </div>
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
      return <ErrorMessage error={error} message="룸 목록을 불러올 수 없습니다." />;
    }

    const hierarchicalRooms = buildRoomHierarchy(rooms);

    if (hierarchicalRooms.length === 0) {
      return (
        <EmptyState
          heading="아직 생성한 룸이 없어요"
          message="좌측 상단의 ‘새 룸’ 버튼을 눌러 새로운 주제를 만들어보세요."
          icon="🗂️"
          tips={[
            '메인 룸을 만들어 전체 프로젝트를 정리하고, 필요하면 하위 룸으로 세부 주제를 나눌 수 있어요.',
            '준비된 문서나 파일이 있다면 업로드하여 팀과 함께 살펴보세요.',
          ]}
        />
      );
    }

    return (
      <div className="room-list">
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
      </div>
    );
  };

  return (
    <div className="room-list-container">
      {renderContent()}
    </div>
  );
};

export default RoomList;
