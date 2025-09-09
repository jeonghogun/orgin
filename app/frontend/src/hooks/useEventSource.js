import { useEffect, useRef, useCallback } from 'react';

const MAX_RECONNECT_ATTEMPTS = 5;
const INITIAL_RECONNECT_DELAY = 1000;

/**
 * A hook to manage a Server-Sent Events (SSE) connection with automatic reconnection.
 * @param {string | null} url The URL to connect to. If null, no connection is made.
 * @param {object} eventListeners An object where keys are event names and values are handler functions.
 * e.g., { delta: (e) => { ... }, done: (e) => { ... } }
 */
const useEventSource = (url, eventListeners) => {
  const eventSourceRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);

  const connect = useCallback(() => {
    if (!url) return;
    if (eventSourceRef.current) eventSourceRef.current.close();

    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onopen = () => {
      console.log('SSE connection opened to', url);
      reconnectAttemptsRef.current = 0;
      if (eventListeners.open) {
        eventListeners.open();
      }
    };

    Object.entries(eventListeners).forEach(([eventName, handler]) => {
      if (eventName !== 'error' && eventName !== 'open') {
        es.addEventListener(eventName, handler);
      }
    });

    es.onerror = (e) => {
      console.error('SSE connection error:', e);
      es.close();

      if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
        const delay = INITIAL_RECONNECT_DELAY * Math.pow(2, reconnectAttemptsRef.current);
        console.log(`Attempting to reconnect SSE in ${delay}ms...`);

        reconnectTimeoutRef.current = setTimeout(() => {
          reconnectAttemptsRef.current++;
          connect();
        }, delay);
      } else {
        console.error('SSE max reconnection attempts reached. Giving up.');
        if (eventListeners.error) {
          eventListeners.error(new Error('Max reconnection attempts reached.'));
        }
      }
    };

  }, [url, eventListeners]);

  useEffect(() => {
    connect();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [connect]);

  // No return value needed, the hook manages the connection internally.
};

export default useEventSource;
