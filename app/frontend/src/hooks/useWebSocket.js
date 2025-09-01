import { useEffect, useRef } from 'react';

const useWebSocket = (roomId, onMessage) => {
  const socketRef = useRef(null);

  useEffect(() => {
    if (!roomId) {
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/rooms/${roomId}`;

    socketRef.current = new WebSocket(wsUrl);

    socketRef.current.onopen = () => {
      console.log(`WebSocket connected to room ${roomId}`);
    };

    socketRef.current.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === 'new_message') {
          onMessage(message.payload);
        }
      } catch (error) {
        console.error('Error parsing incoming WebSocket message:', error);
      }
    };

    socketRef.current.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    socketRef.current.onclose = () => {
      console.log(`WebSocket disconnected from room ${roomId}`);
    };

    return () => {
      if (socketRef.current) {
        socketRef.current.close();
      }
    };
  }, [roomId, onMessage]);
};

export default useWebSocket;
