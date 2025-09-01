import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { ROOM_TYPES } from '../constants';
import { useAppContext } from '../context/AppContext';

const fetchRooms = async () => {
  try {
    const response = await axios.get('/api/rooms');
    
    // 응답 데이터 유효성 검사
    if (!response.data) {
      console.warn('fetchRooms: No data in response');
      return [];
    }
    
    if (!Array.isArray(response.data)) {
      console.warn('fetchRooms: Response data is not an array:', response.data);
      return [];
    }
    
    return response.data;
  } catch (error) {
    console.error('fetchRooms error:', error);
    throw error;
  }
};

const buildRoomHierarchy = (rooms) => {
  // rooms가 배열이 아니거나 undefined/null인 경우 빈 배열 반환
  if (!rooms || !Array.isArray(rooms)) {
    console.warn('buildRoomHierarchy: rooms is not an array:', rooms);
    return [];
  }
  
  // 빈 배열인 경우 빈 배열 반환
  if (rooms.length === 0) {
    return [];
  }
  
  try {
    const roomMap = new Map();
    const validRooms = rooms.filter(room => room && room.room_id && typeof room.room_id === 'string');
    
    // 유효한 room만 처리
    validRooms.forEach(room => {
      room.children = [];
      roomMap.set(room.room_id, room);
    });

    const hierarchy = [];
    validRooms.forEach(room => {
      if (room.parent_id && roomMap.has(room.parent_id)) {
        const parent = roomMap.get(room.parent_id);
        if (parent) {
          parent.children.push(room);
        } else {
          hierarchy.push(room);
        }
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

const RoomItem = ({ room, level, parentRoom = null }) => {
  const { handleRoomSelect, handleToggleReview, selectedRoomId } = useAppContext();
  const [isHovered, setIsHovered] = useState(false);
  const isReviewRoom = room.type === ROOM_TYPES.REVIEW || level === 2;
  const indent = level * 12;
  const isActive = selectedRoomId === room.room_id;

  const handleClick = () => {
    if (isReviewRoom) {
      // 검토룸 클릭 시 부모 세부룸 정보도 함께 전달
      const reviewData = {
        ...room,
        parent_room: parentRoom, // 부모 세부룸 정보
        sub_room_id: parentRoom?.room_id // 세부룸 ID
      };
      handleToggleReview(reviewData);
    } else {
      handleRoomSelect(room.room_id);
    }
  };

  return (
    <>
      <div
        className={`flex items-center gap-3 px-4 py-2 cursor-pointer transition-colors duration-150 ${
          isActive ? 'bg-accent/10 border-l-2 border-accent' : 'hover:bg-white/5'
        }`}
        style={{ paddingLeft: `${16 + indent}px` }}
        onClick={handleClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
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
              parentRoom={room} // 부모 룸 정보 전달
            />
          ))}
        </div>
      )}
    </>
  );
};

const Sidebar = () => {
  const { sidebarOpen, setSidebarOpen, handleRoomSelect } = useAppContext();
  const queryClient = useQueryClient();

  const { data: rooms = [], error, isLoading } = useQuery({
    queryKey: ['rooms'],
    queryFn: fetchRooms,
    enabled: true, // 항상 활성화
    initialData: [], // 초기 데이터를 빈 배열로 설정
    retry: 1, // 재시도 횟수 제한
  });

  const renderContent = () => {
    if (isLoading) {
      return (
        <div className="flex items-center justify-center p-8">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-accent"></div>
        </div>
      );
    }

    if (error) {
      console.error('Sidebar error:', error);
      return (
        <div className="p-4 text-danger text-body">
          룸 목록을 불러올 수 없습니다.
        </div>
      );
    }

    // rooms가 undefined, null, 또는 배열이 아닌 경우 처리
    if (!rooms || !Array.isArray(rooms)) {
      console.warn('renderContent: rooms is not an array:', rooms);
      return (
        <div className="p-4 text-muted text-body text-center">
          룸 데이터를 불러올 수 없습니다.
        </div>
      );
    }

    const hierarchicalRooms = buildRoomHierarchy(rooms);

    if (!hierarchicalRooms || hierarchicalRooms.length === 0) {
      return (
        <div className="p-4 text-muted text-body text-center">
          룸이 없습니다. 시작하려면 하나를 만드세요.
        </div>
      );
    }

    return (
      <div className="space-y-1">
        {hierarchicalRooms.map((room) => {
          if (!room || !room.room_id) {
            console.warn('renderContent: Invalid room data:', room);
            return null;
          }
          
          return (
            <RoomItem
              key={room.room_id}
              room={room}
              level={0}
            />
          );
        }).filter(Boolean)} {/* null 값 제거 */}
      </div>
    );
  };

  const onToggle = () => setSidebarOpen(!sidebarOpen);
  const onClose = () => setSidebarOpen(false);

  return (
    <>
      {/* 모바일에서 사이드바가 닫혔을 때 열기 버튼 */}
      {!sidebarOpen && (
        <button
          onClick={onToggle}
          className="fixed top-4 left-4 z-50 p-2 bg-panel border border-border rounded-button hover:bg-panel-elev transition-colors duration-150 focus-ring"
        >
          <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4 text-text">
            <path d="M2 4h12v1H2V4zm0 3h12v1H2V7zm0 3h12v1H2v-1z"/>
          </svg>
        </button>
      )}

      {/* 사이드바 */}
      <div className={`fixed lg:relative inset-y-0 left-0 z-40 bg-panel border-r border-border flex flex-col h-full
        transition-all duration-150 ease-out
        ${sidebarOpen ? 'w-[280px] translate-x-0' : 'w-0 -translate-x-full lg:w-[280px] lg:translate-x-0'}
      `}>
        {/* 사이드바 내용 - 항상 렌더링하되 너비만 조절 */}
        <div className="flex flex-col h-full w-[280px]">
          {/* 헤더 - 고정 */}
          <div className="flex items-center justify-between p-4 border-b border-border flex-shrink-0">
            <button className="btn-primary text-body flex items-center" onClick={() => handleRoomSelect(null)}> {/* 새 채팅 버튼 클릭 시 메인 룸으로 이동 */}
              <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4 mr-2">
                <path d="M8 0C3.6 0 0 3.6 0 8s3.6 8 8 8 8-3.6 8-8-3.6-8-8-8zm4 9H7v5H5V9H0V7h5V2h2v5h5v2z"/>
              </svg>
              새채팅
            </button>
            <button
              onClick={onClose}
              className="p-2 text-muted hover:text-text transition-colors duration-150 focus-ring lg:hidden"
            >
              <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4">
                <path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/>
              </svg>
            </button>
          </div>

          {/* 룸 목록 - 독립 스크롤 */}
          <div className="flex-1 overflow-y-auto overflow-x-hidden">
            {renderContent()}
          </div>
        </div>
      </div>

      {/* 모바일 오버레이 */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden"
          onClick={onClose}
        />
      )}
    </>
  );
};

export default Sidebar;
