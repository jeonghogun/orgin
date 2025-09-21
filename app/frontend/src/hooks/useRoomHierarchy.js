import { useMemo } from 'react';

export const buildRoomHierarchy = (rooms) => {
  if (!Array.isArray(rooms) || rooms.length === 0) {
    return [];
  }

  const roomMap = new Map();
  const roomNodes = [];

  rooms.forEach((room) => {
    if (!room || !room.room_id) {
      return;
    }

    const roomCopy = { ...room, children: [] };
    roomMap.set(roomCopy.room_id, roomCopy);
    roomNodes.push(roomCopy);
  });

  const hierarchy = [];

  roomNodes.forEach((room) => {
    const parentId = room.parent_id;
    if (parentId && roomMap.has(parentId)) {
      const parent = roomMap.get(parentId);
      parent.children.push(room);
    } else {
      hierarchy.push(room);
    }
  });

  return hierarchy;
};

const useRoomHierarchy = (rooms) => {
  return useMemo(() => buildRoomHierarchy(rooms), [rooms]);
};

export default useRoomHierarchy;
