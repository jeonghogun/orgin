import { useEffect, useRef, useState } from 'react';

const useWebSocket = (roomId, onMessage) => {
  const socketRef = useRef(null);
  const [isConnected, setIsConnected] = useState(false);
  const reconnectTimeoutRef = useRef(null);

  useEffect(() => {
    if (!roomId) {
      return;
    }

    const connectWebSocket = () => {
      // 기존 연결이 있다면 정리
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        socketRef.current.close();
      }

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const wsUrl = `${protocol}//${host}/ws/rooms/${roomId}`;

      // Attempt to get the auth token from localStorage.
      const token = localStorage.getItem('firebaseIdToken') || localStorage.getItem('authToken');

      try {
        socketRef.current = new WebSocket(wsUrl, token ? [token] : undefined);

        socketRef.current.onopen = () => {
          console.log(`WebSocket connected to room ${roomId}`);
          setIsConnected(true);
          
          // 재연결 타이머 클리어
          if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
            reconnectTimeoutRef.current = null;
          }
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
          setIsConnected(false);
        };

        socketRef.current.onclose = (event) => {
          console.log(`WebSocket disconnected from room ${roomId}`, event.code, event.reason);
          setIsConnected(false);
          
          // 정상적인 종료가 아닌 경우에만 재연결 시도
          if (event.code !== 1000 && event.code !== 1001) {
            console.log(`Attempting to reconnect to room ${roomId} in 3 seconds...`);
            reconnectTimeoutRef.current = setTimeout(() => {
              if (roomId) {
                connectWebSocket();
              }
            }, 3000);
          }
        };
      } catch (error) {
        console.error('Failed to create WebSocket connection:', error);
        setIsConnected(false);
      }
    };

    // 초기 연결
    connectWebSocket();

    // Cleanup function
    return () => {
      // 재연결 타이머 클리어
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      
      // WebSocket 연결 종료 (정상 종료 코드 사용)
      if (socketRef.current) {
        if (socketRef.current.readyState === WebSocket.OPEN) {
          socketRef.current.close(1000, 'Component unmounting');
        }
        socketRef.current = null;
      }
    };
  }, [roomId, onMessage]);

  // 연결 상태 반환
  return { isConnected };
};

export default useWebSocket;
