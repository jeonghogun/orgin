import { create } from 'zustand';

const useRoomStore = create((set) => ({
  rooms: [],
  selectedRoomId: null,
  setRooms: (rooms) => set({ rooms }),
  setSelectedRoomId: (roomId) => set({ selectedRoomId: roomId }),
  // We can add more actions later, e.g., for creating/deleting rooms
}));

export default useRoomStore;
