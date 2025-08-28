import { useState, useEffect, useRef, useCallback } from 'react';

const MAX_RECONNECT_ATTEMPTS = 5;
const INITIAL_RECONNECT_DELAY = 1000; // 1 second

const useReviewSocket = (reviewId, token) => {
  const [status, setStatus] = useState('pending');
  const [error, setError] = useState(null);
  const websocket = useRef(null);
  const reconnectAttempts = useRef(0);
  const processedMessageIds = useRef(new Set());

  const connect = useCallback(() => {
    if (!reviewId || !token) {
      return;
    }
    if (websocket.current && websocket.current.readyState === WebSocket.OPEN) {
      console.log('WebSocket already connected.');
      return;
    }

    const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${wsProtocol}://${window.location.host}/ws/reviews/${reviewId}`;

    // Pass the token as the second argument in the subprotocol array
    websocket.current = new WebSocket(wsUrl, ['graphql-ws', token]);

    websocket.current.onopen = () => {
      console.log('WebSocket connected for review:', reviewId);
      setStatus('connected');
      reconnectAttempts.current = 0; // Reset on successful connection
    };

    websocket.current.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        console.log('WebSocket message received:', message);

        // Deduplication using a message ID (assuming server sends one)
        const messageId = message.ts; // Using timestamp as a unique ID
        if (processedMessageIds.current.has(messageId)) {
          console.log('Skipping duplicate message:', messageId);
          return;
        }
        processedMessageIds.current.add(messageId);

        if (message.type === 'status_update' && message.payload && message.payload.status) {
          setStatus(message.payload.status);
        }
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };

    websocket.current.onerror = (err) => {
      console.error('WebSocket error:', err);
      setError('WebSocket connection error.');
    };

    websocket.current.onclose = (event) => {
      console.log(`WebSocket disconnected for review ${reviewId}:`, event.code, event.reason);
      if (event.code === 1008) { // Policy Violation
        setError("Connection closed due to authorization failure.");
        return; // Do not reconnect on auth errors
      }

      if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
        const delay = INITIAL_RECONNECT_DELAY * Math.pow(2, reconnectAttempts.current);
        console.log(`Attempting to reconnect in ${delay}ms...`);
        setTimeout(() => {
          reconnectAttempts.current++;
          connect();
        }, delay);
      } else {
        setError('Could not reconnect to WebSocket after multiple attempts.');
      }
    };
  }, [reviewId, token]);

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
      setError('Network connection lost.');
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    connect();

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      if (websocket.current) {
        websocket.current.close();
      }
    };
  }, [connect]);

  return { status, error };
};

export default useReviewSocket;
