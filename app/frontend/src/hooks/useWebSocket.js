import { useState, useEffect, useRef, useCallback } from 'react';

const MAX_RECONNECT_ATTEMPTS = 5;
const INITIAL_RECONNECT_DELAY = 1000; // 1 second

/**
 * A generic WebSocket hook with automatic reconnection logic.
 * @param {string | null} url The WebSocket URL to connect to. If null, no connection is made.
 * @param {function} onMessage A callback function to handle incoming messages.
 * @param {string | null} token An optional authentication token.
 * @returns {{ connectionStatus: 'idle' | 'connecting' | 'connected' | 'disconnected' | 'reconnecting' | 'failed' | 'error' }}
 */
const useWebSocket = (url, onMessage, token = null) => {
  const [connectionStatus, setConnectionStatus] = useState('idle');
  const websocket = useRef(null);
  const reconnectAttempts = useRef(0);
  const processedMessageIds = useRef(new Set());

  const connect = useCallback(() => {
    if (!url) {
      return;
    }
    if (websocket.current && websocket.current.readyState === WebSocket.OPEN) {
      console.log('WebSocket already connected.');
      return;
    }

    setConnectionStatus('connecting');

    // The WebSocket constructor handles the token presence correctly.
    websocket.current = new WebSocket(url, token ? ['graphql-ws', token] : undefined);

    websocket.current.onopen = () => {
      console.log('WebSocket connected to:', url);
      setConnectionStatus('connected');
      reconnectAttempts.current = 0;
    };

    websocket.current.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);

        // Use a timestamp or a unique message ID for deduplication if available
        const messageId = message.id || message.ts || message.timestamp;
        if (messageId && processedMessageIds.current.has(messageId)) {
          console.log('Skipping duplicate message:', messageId);
          return;
        }
        if (messageId) {
          processedMessageIds.current.add(messageId);
        }

        onMessage(message);
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };

    websocket.current.onerror = (err) => {
      console.error('WebSocket error:', err);
      setConnectionStatus('error');
    };

    websocket.current.onclose = (event) => {
      console.log(`WebSocket disconnected:`, event.code, event.reason);
      setConnectionStatus('disconnected');

      // Do not reconnect on normal closure or policy violations
      if (event.code === 1000 || event.code === 1001 || event.code === 1008) {
        if (event.code === 1008) setConnectionStatus('failed');
        return;
      }

      if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
        const delay = INITIAL_RECONNECT_DELAY * Math.pow(2, reconnectAttempts.current);
        console.log(`Attempting to reconnect in ${delay}ms...`);
        setConnectionStatus('reconnecting');
        setTimeout(() => {
          reconnectAttempts.current++;
          connect();
        }, delay);
      } else {
        console.error('Could not reconnect to WebSocket after multiple attempts.');
        setConnectionStatus('failed');
      }
    };
  }, [url, onMessage, token]);

  useEffect(() => {
    const handleOnline = () => {
      console.log('Browser is online. Attempting to connect WebSocket.');
      connect();
    };
    const handleOffline = () => {
      console.log('Browser is offline. Closing WebSocket.');
      if (websocket.current) {
        websocket.current.close();
      }
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    connect();

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      if (websocket.current) {
        websocket.current.close(1000); // Normal closure
      }
    };
  }, [connect]);

  return { connectionStatus };
};

export default useWebSocket;
