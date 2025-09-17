import React, { useState, useMemo, useCallback, memo, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ROOM_TYPES } from '../constants';
import { startRoomCreation } from '../store/useConversationStore';
import { useAppContext } from '../context/AppContext';
import RenameRoomModal from './modals/RenameRoomModal';
import DeleteConfirmationModal from './modals/DeleteConfirmationModal';

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

const RoomItem = memo(({ room, level, parentRoom = null, onRenameClick, onDeleteClick, onCreateSubRoom, onCreateReviewRoom }) => {
  const { handleRoomSelect } = useAppContext();
  const { roomId: activeRoomId } = useParams();
  const [isMenuOpen, setMenuOpen] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  const isReviewRoom = room.type === ROOM_TYPES.REVIEW;
  const indent = level * 12;

  const isActive = activeRoomId === room.room_id;

  const getLinkDestination = useCallback(() => {
    return `/rooms/${room.room_id}`;
  }, [room.room_id]);

  const onRoomSelect = useCallback(() => handleRoomSelect(room.room_id), [handleRoomSelect, room.room_id]);

  const handleMenuClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setMenuOpen(!isMenuOpen);
  };

  const handleRename = (e) => {
    e.preventDefault();
    e.stopPropagation();
    onRenameClick(room);
    setMenuOpen(false);
  };

  const handleDelete = (e) => {
    e.preventDefault();
    e.stopPropagation();
    onDeleteClick(room);
    setMenuOpen(false);
  };

  const handleAddSubRoom = (e) => {
    e.preventDefault();
    e.stopPropagation();
    console.log('+ button clicked for sub room, room_id:', room.room_id);
    onCreateSubRoom(room.room_id);
  };

  const handleAddReviewRoom = (e) => {
    e.preventDefault();
    e.stopPropagation();
    console.log('+ button clicked for review room, room_id:', room.room_id);
    onCreateReviewRoom(room.room_id);
  };

  return (
    <div
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => {
        setIsHovered(false);
        setMenuOpen(false);
      }}
      className="relative"
    >
      <Link to={getLinkDestination()} onClick={onRoomSelect} className="block">
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
          <span className={`flex-1 text-body truncate ${isReviewRoom ? 'text-muted' : 'text-text'}`}>
            {isReviewRoom
              ? (room.name?.startsWith('검토') ? room.name : `검토: ${room.name}`)
              : room.name}
          </span>

          {isHovered && (
            <div className="flex items-center gap-1">
              {/* + 버튼 - 메인룸과 세부룸에만 표시 */}
              {(room.type === ROOM_TYPES.MAIN || room.type === ROOM_TYPES.SUB) && (
                <button 
                  onClick={room.type === ROOM_TYPES.MAIN ? handleAddSubRoom : handleAddReviewRoom}
                  className="p-1 rounded-full hover:bg-white/10 text-muted hover:text-text"
                  title={room.type === ROOM_TYPES.MAIN ? "세부룸 추가" : "검토룸 추가"}
                >
                  <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4">
                    <path d="M8 0C3.6 0 0 3.6 0 8s3.6 8 8 8 8-3.6 8-8-3.6-8-8-8zm4 9H7v5H5V9H0V7h5V2h2v5h5v2z"/>
                  </svg>
                </button>
              )}
              
              {/* 메뉴 버튼 - 메인룸이 아닌 경우에만 표시 */}
              {room.type !== ROOM_TYPES.MAIN && (
                <div className="relative">
                  <button onClick={handleMenuClick} className="p-1 rounded-full hover:bg-white/10">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
                    </svg>
                  </button>
                  {isMenuOpen && (
                    <div className="absolute right-0 mt-2 w-32 bg-panel-elev border border-border rounded-md shadow-lg z-10">
                      <button onClick={handleRename} className="w-full text-left px-4 py-2 text-sm text-text hover:bg-white/5">이름 변경</button>
                      <button onClick={handleDelete} className="w-full text-left px-4 py-2 text-sm text-danger hover:bg-white/5">삭제</button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </Link>
      {room.children && room.children.length > 0 && (
        <div>
          {room.children.map(child => (
            <RoomItem
              key={child.room_id}
              room={child}
              level={level + 1}
              parentRoom={room}
              onRenameClick={onRenameClick}
              onDeleteClick={onDeleteClick}
              onCreateSubRoom={onCreateSubRoom}
              onCreateReviewRoom={onCreateReviewRoom}
            />
          ))}
        </div>
      )}
    </div>
  );
});

const Sidebar = memo(() => {
  const { sidebarOpen, setSidebarOpen, initiateRoomCreation, showError, handleRoomSelect } = useAppContext();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [renamingRoom, setRenamingRoom] = useState(null);
  const [deletingRoom, setDeletingRoom] = useState(null);

  const { data: rooms = [], error, isLoading } = useQuery({
    queryKey: ['rooms'],
    queryFn: fetchRooms,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });


  const renameMutation = useMutation({
    mutationFn: async ({ roomId, newName }) => {
      const { data } = await axios.patch(`/api/rooms/${roomId}`, { name: newName });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rooms'] });
      setRenamingRoom(null);
    },
    onError: () => {
      showError('룸 이름 변경에 실패했습니다.');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (roomId) => {
      await axios.delete(`/api/rooms/${roomId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rooms'] });
      setDeletingRoom(null);
      navigate('/'); // Redirect to home after deletion
    },
    onError: () => {
      showError('룸 삭제에 실패했습니다.');
    },
  });


  const hierarchicalRooms = useMemo(() => buildRoomHierarchy(rooms), [rooms]);

  const handleCreateSubRoom = useCallback((parentId) => {
    const promptText = "어떤 세부룸을 만들까요?";
    startRoomCreation(parentId, ROOM_TYPES.SUB, promptText);
    queryClient.setQueryData(['messages', parentId], (old = []) => [
      ...old,
      {
        message_id: `ai_prompt_${Date.now()}`,
        room_id: parentId,
        role: 'assistant',
        content: promptText,
        timestamp: Math.floor(Date.now() / 1000),
      }
    ]);
  }, [startRoomCreation, queryClient]);

  const handleCreateReviewRoom = useCallback((parentId) => {
    const promptText = "어떤 주제로 검토룸을 열까요?";
    startRoomCreation(parentId, ROOM_TYPES.REVIEW, promptText);
    queryClient.setQueryData(['messages', parentId], (old = []) => [
      ...old,
      {
        message_id: `ai_prompt_${Date.now()}`,
        room_id: parentId,
        role: 'assistant',
        content: promptText,
        timestamp: Math.floor(Date.now() / 1000),
      }
    ]);
  }, [startRoomCreation, queryClient]);

  const handleRenameClick = useCallback((room) => setRenamingRoom(room), []);
  const handleDeleteClick = useCallback((room) => setDeletingRoom(room), []);

  const handleCloseRenameModal = useCallback(() => setRenamingRoom(null), []);
  const handleCloseDeleteModal = useCallback(() => setDeletingRoom(null), []);

  const handleRenameSave = useCallback((newName) => {
    if (renamingRoom) {
      renameMutation.mutate({ roomId: renamingRoom.room_id, newName });
    }
  }, [renamingRoom, renameMutation]);

  const handleDeleteConfirm = useCallback(() => {
    if (deletingRoom) {
      deleteMutation.mutate(deletingRoom.room_id);
    }
  }, [deletingRoom, deleteMutation]);

  const onClose = useCallback(() => setSidebarOpen(false), [setSidebarOpen]);

  const renderContent = () => {
    if (isLoading) {
      return <div className="flex items-center justify-center p-8"><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-accent"></div></div>;
    }
    if (error) {
      return <div className="p-4 text-danger text-body">룸 목록을 불러올 수 없습니다.</div>;
    }
    if (hierarchicalRooms.length === 0) {
      return <div className="p-4 text-muted text-body text-center">메인룸을 생성하는 중...</div>;
    }
    return (
      <div className="space-y-1">
        {hierarchicalRooms.map((room) => (
          <RoomItem
            key={room.room_id}
            room={room}
            level={0}
            onRenameClick={handleRenameClick}
            onDeleteClick={handleDeleteClick}
            onCreateSubRoom={handleCreateSubRoom}
            onCreateReviewRoom={handleCreateReviewRoom}
          />
        ))}
      </div>
    );
  };

  return (
    <>
      {!sidebarOpen && (
        <button onClick={() => setSidebarOpen(true)} className="fixed top-4 left-4 z-50 p-2 bg-panel border border-border rounded-button hover:bg-panel-elev transition-colors">
          <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4 text-text"><path d="M2 4h12v1H2V4zm0 3h12v1H2V7zm0 3h12v1H2v-1z"/></svg>
        </button>
      )}
      <div className={`h-full bg-panel border-r border-border flex flex-col transition-all duration-150 ${sidebarOpen ? 'w-[280px]' : 'w-0'}`}>
        {sidebarOpen && (
          <div className="flex flex-col h-full w-[280px]">
            <div className="flex items-center justify-between p-4 border-b border-border flex-shrink-0">
              <h2 className="text-h3 text-text font-semibold">채팅룸</h2>
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

      <RenameRoomModal
        isOpen={!!renamingRoom}
        room={renamingRoom}
        onClose={handleCloseRenameModal}
        onSave={handleRenameSave}
      />
      <DeleteConfirmationModal
        isOpen={!!deletingRoom}
        room={deletingRoom}
        onClose={handleCloseDeleteModal}
        onConfirm={handleDeleteConfirm}
      />
    </>
  );
});

export default Sidebar;
