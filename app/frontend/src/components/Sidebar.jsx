import React, { useState, useMemo, useCallback, memo } from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ROOM_TYPES } from '../constants';
import { useAppContext } from '../context/AppContext';

const fetchRooms = async () => {
  try {
    const response = await axios.get('/api/rooms');
    if (!response.data || !Array.isArray(response.data)) {
      console.warn('fetchRooms: Invalid data received', response.data);
      return [];
    }
    return response.data;
  } catch (error) {
    console.error('fetchRooms error:', error);
    throw error;
  }
};

const buildRoomHierarchy = (rooms) => {
  if (!Array.isArray(rooms) || rooms.length === 0) {
    return [];
  }
  try {
    const roomMap = new Map();
    const validRooms = rooms.filter(room => room && room.room_id);
    
    validRooms.forEach(room => {
      room.children = [];
      roomMap.set(room.room_id, room);
    });

    const hierarchy = [];
    validRooms.forEach(room => {
      if (room.parent_id && roomMap.has(room.parent_id)) {
        roomMap.get(room.parent_id)?.children.push(room);
      } else {
        hierarchy.push(room);
      }
    });
    return hierarchy;
  } catch (error) {
    console.error('buildRoomHierarchy error:', error);
    return [];
  }
};

const RoomItem = memo(({ room, level, parentRoom = null }) => {
  const { handleRoomSelect } = useAppContext();
  const { roomId: activeRoomId } = useParams();

  const isReviewRoom = room.type === ROOM_TYPES.REVIEW || level === 2;
  const indent = level * 12;

  const isActive = isReviewRoom
    ? activeRoomId === parentRoom?.room_id
    : activeRoomId === room.room_id;

  const getLinkDestination = useCallback(() => {
    if (isReviewRoom && parentRoom) {
      return window.innerWidth >= 1024
        ? `/rooms/${parentRoom.room_id}/reviews/${room.room_id}`
        : `/reviews/${room.room_id}`;
    }
    return `/rooms/${room.room_id}`;
  }, [isReviewRoom, parentRoom, room.room_id]);

  const onRoomSelect = useCallback(() => handleRoomSelect(room.room_id), [handleRoomSelect, room.room_id]);

  return (
    <Link to={getLinkDestination()} onClick={onRoomSelect}>
      <div
        className={`flex items-center gap-3 px-4 py-2 cursor-pointer transition-colors duration-150 ${
          isActive ? 'bg-accent/10 border-l-2 border-accent' : 'hover:bg-white/5'
        }`}
        style={{ paddingLeft: `${16 + indent}px` }}
      >
        <div className="w-4 h-4 flex-shrink-0">
          {isReviewRoom ? (
            <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4 text-muted">
              <path d="M8 0C3.6 0 0 3.6 0 8s3.6 8 8 8 8-3.6 8-8-3.6-8-8-8zm0 14c-3.3 0-6-2.7-6-6s2.7-6 6-6 6 2.7 6 6-2.7 6-6 6z"/>
            </svg>
          ) : (
            <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4 text-muted">
              <path d="M14 1H2C1.4 1 1 1.4 1 2v10c0 .6.4 1 1 1h2l3 3 3-3h5c.6 0 1-.4 1-1V2c0-.6-.4-1-1-1z"/>
            </svg>
          )}
        </div>
        <span className={`text-body truncate ${isReviewRoom ? 'text-muted' : 'text-text'}`}>
          {isReviewRoom ? `검토: ${room.name}` : room.name}
        </span>
      </div>
      {room.children && room.children.length > 0 && (
        <div>
          {room.children.map(child => (
            <RoomItem
              key={child.room_id}
              room={child}
              level={level + 1}
              parentRoom={room}
            />
          ))}
        </div>
      )}
    </Link>
  );
});

const Sidebar = memo(() => {
  const { sidebarOpen, setSidebarOpen, handleRoomSelect } = useAppContext();
  const navigate = useNavigate();

  const { data: rooms = [], error, isLoading } = useQuery({
    queryKey: ['rooms'],
    queryFn: fetchRooms,
    staleTime: 5 * 60 * 1000, // 5 minute stale time
    retry: 1,
  });

  const hierarchicalRooms = useMemo(() => buildRoomHierarchy(rooms), [rooms]);

  const handleNewChat = useCallback(() => {
    handleRoomSelect(null);
    navigate('/');
  }, [handleRoomSelect, navigate]);

  const onClose = useCallback(() => setSidebarOpen(false), [setSidebarOpen]);

  const renderContent = () => {
    if (isLoading) {
      return (
        <div className="flex items-center justify-center p-8">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-accent"></div>
        </div>
      );
    }
    if (error) {
      return <div className="p-4 text-danger text-body">룸 목록을 불러올 수 없습니다.</div>;
    }
    if (hierarchicalRooms.length === 0) {
      return <div className="p-4 text-muted text-body text-center">룸이 없습니다.</div>;
    }
    return (
      <div className="space-y-1">
        {hierarchicalRooms.map((room) => (
          <RoomItem key={room.room_id} room={room} level={0} />
        ))}
      </div>
    );
  };

  return (
    <>
      {!sidebarOpen && (
        <button
          onClick={() => setSidebarOpen(true)}
          className="fixed top-4 left-4 z-50 p-2 bg-panel border border-border rounded-button hover:bg-panel-elev transition-colors"
        >
          <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4 text-text"><path d="M2 4h12v1H2V4zm0 3h12v1H2V7zm0 3h12v1H2v-1z"/></svg>
        </button>
      )}
      <div className={`h-full bg-panel border-r border-border flex flex-col transition-all duration-150 ${sidebarOpen ? 'w-[280px]' : 'w-0'}`}>
        {sidebarOpen && (
          <div className="flex flex-col h-full w-[280px]">
            <div className="flex items-center justify-between p-4 border-b border-border flex-shrink-0">
              <button className="btn-primary text-body flex items-center" onClick={handleNewChat}>
                <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4 mr-2"><path d="M8 0C3.6 0 0 3.6 0 8s3.6 8 8 8 8-3.6 8-8-3.6-8-8-8zm4 9H7v5H5V9H0V7h5V2h2v5h5v2z"/></svg>
                새채팅
              </button>
              <button onClick={onClose} className="p-2 text-muted hover:text-text lg:hidden">
                <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4"><path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/></svg>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto overflow-x-hidden">
              {renderContent()}
            </div>
          </div>
        )}
      </div>
      {sidebarOpen && <div className="fixed inset-0 bg-black/50 z-30 lg:hidden" onClick={onClose} />}
    </>
  );
});

export default Sidebar;
