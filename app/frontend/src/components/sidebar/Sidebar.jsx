import React, { useEffect, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { useNavigate, useParams } from 'react-router-dom';
import useRoomStore from '../../store/useRoomStore';
import { ROOM_TYPES } from '../../constants';
import { PlusIcon, ChevronDownIcon, ChevronRightIcon } from '@heroicons/react/24/solid';

const RoomItem = ({ room, level = 0 }) => {
  const { selectedRoomId, setSelectedRoomId } = useRoomStore();
  const navigate = useNavigate();
  const [isExpanded, setIsExpanded] = React.useState(true);

  const handleSelectRoom = () => {
    setSelectedRoomId(room.room_id);
    // Navigate to a URL that reflects the selected room, for example
    navigate(`/rooms/${room.room_id}`);
  };

  const isSelected = selectedRoomId === room.room_id;

  return (
    <div>
      <div
        onClick={handleSelectRoom}
        style={{ paddingLeft: `${level * 1.5}rem` }}
        className={`flex items-center justify-between p-2 rounded-lg cursor-pointer ${
          isSelected ? 'bg-accent text-white' : 'hover:bg-panel-elev'
        }`}
      >
        <span className="truncate">{room.name}</span>
        {room.children && room.children.length > 0 && (
          <button onClick={(e) => { e.stopPropagation(); setIsExpanded(!isExpanded); }} className="p-1">
            {isExpanded ? <ChevronDownIcon className="w-4 h-4" /> : <ChevronRightIcon className="w-4 h-4" />}
          </button>
        )}
      </div>
      {isExpanded && room.children && (
        <div className="mt-1">
          {room.children.map((child) => (
            <RoomItem key={child.room_id} room={child} level={level + 1} />
          ))}
        </div>
      )}
    </div>
  );
};


const Sidebar = () => {
  const { rooms, setRooms, selectedRoomId, setSelectedRoomId } = useRoomStore();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { roomId } = useParams();

  const { data: fetchedRooms, isLoading, error } = useQuery({
    queryKey: ['rooms'],
    queryFn: async () => {
      const { data } = await axios.get('/api/rooms');
      return data;
    },
    onSuccess: (data) => {
      setRooms(data);
    },
  });

  useEffect(() => {
    if (roomId) {
      setSelectedRoomId(roomId);
    } else if (rooms.length > 0 && !selectedRoomId) {
      // If no room is selected, default to the first main room
      const mainRoom = rooms.find(r => r.type === ROOM_TYPES.MAIN);
      if (mainRoom) {
        setSelectedRoomId(mainRoom.room_id);
        navigate(`/rooms/${mainRoom.room_id}`);
      }
    }
  }, [roomId, rooms, selectedRoomId, setSelectedRoomId, navigate]);

  const roomTree = useMemo(() => {
    const roomMap = {};
    const tree = [];

    rooms.forEach(room => {
      roomMap[room.room_id] = { ...room, children: [] };
    });

    rooms.forEach(room => {
      if (room.parent_id && roomMap[room.parent_id]) {
        roomMap[room.parent_id].children.push(roomMap[room.room_id]);
      } else {
        tree.push(roomMap[room.room_id]);
      }
    });

    // Sort children by name
    Object.values(roomMap).forEach(room => {
        room.children.sort((a, b) => a.name.localeCompare(b.name));
    });

    // Sort root level rooms by name
    tree.sort((a, b) => a.name.localeCompare(b.name));

    return tree;
  }, [rooms]);

  const createRoomMutation = useMutation({
    mutationFn: async ({ name, type, parentId }) => {
      const { data } = await axios.post('/api/rooms', { name, type, parent_id: parentId });
      return data;
    },
    onSuccess: (newRoom) => {
      queryClient.invalidateQueries({ queryKey: ['rooms'] });
      setSelectedRoomId(newRoom.room_id);
      navigate(`/rooms/${newRoom.room_id}`);
    },
    onError: (error) => {
      console.error('Failed to create room:', error);
      alert('Error: ' + error.response?.data?.detail || 'Could not create room.');
    },
  });

  const handleNewSubRoom = () => {
    const selectedRoom = rooms.find(r => r.room_id === selectedRoomId);
    if (!selectedRoom || selectedRoom.type !== ROOM_TYPES.MAIN) {
      alert('Please select a main room to add a sub-room.');
      return;
    }
    const name = prompt('Enter the name for the new Sub Room:');
    if (name) {
      createRoomMutation.mutate({ name, type: ROOM_TYPES.SUB, parentId: selectedRoomId });
    }
  };

  const handleNewReviewRoom = () => {
    const selectedRoom = rooms.find(r => r.room_id === selectedRoomId);
    if (!selectedRoom || selectedRoom.type !== ROOM_TYPES.SUB) {
      alert('Please select a sub-room to add a review room.');
      return;
    }
    const name = prompt('Enter the name for the new Review Room:');
    if (name) {
      createRoomMutation.mutate({ name, type: ROOM_TYPES.REVIEW, parentId: selectedRoomId });
    }
  };


  if (isLoading) return <div className="p-4">Loading rooms...</div>;
  if (error) return <div className="p-4 text-danger">Error loading rooms.</div>;

  return (
    <div className="w-72 h-screen bg-panel text-text p-4 flex flex-col">
      <h1 className="text-h1 mb-4">Rooms</h1>
      <div className="space-y-2 mb-4">
        <button onClick={handleNewSubRoom} className="w-full flex items-center justify-center p-2 rounded-button bg-accent hover:bg-accent-weak">
            <PlusIcon className="w-5 h-5 mr-2"/> New Sub Room
        </button>
        <button onClick={handleNewReviewRoom} className="w-full flex items-center justify-center p-2 rounded-button bg-accent hover:bg-accent-weak">
            <PlusIcon className="w-5 h-5 mr-2"/> New Review Room
        </button>
      </div>
      <div className="flex-1 overflow-y-auto space-y-1 pr-2">
        {roomTree.map((room) => (
          <RoomItem key={room.room_id} room={room} />
        ))}
      </div>
    </div>
  );
};

export default Sidebar;
