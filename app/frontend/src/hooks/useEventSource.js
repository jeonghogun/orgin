import { useEffect, useRef, useCallback, useState, useMemo } from 'react';
import { SSE } from 'sse.js';
import { resolveApiUrl } from '../lib/apiClient';

const MAX_RECONNECT_ATTEMPTS = 3;
const INITIAL_RECONNECT_DELAY = 2000;

/**
 * A hook to manage a Server-Sent Events (SSE) connection with specific event handlers
 * and robust error handling/reconnection logic.
 * @param {string | null} url The URL to connect to. If null, no connection is made.
 * @param {object} eventListeners An object where keys are event names and values are handler functions.
 * e.g., { delta: (e) => { ... }, done: (e) => { ... }, error: (e) => { ... } }
 */
const useEventSource = (url, eventListeners, options = {}) => {
  const eventSourceRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);
  const [status, setStatus] = useState('idle');
  const [lastError, setLastError] = useState(null);
  const resolvedUrl = useMemo(() => (url ? resolveApiUrl(url) : null), [url]);

  const closeConnection = useCallback((nextStatus = 'disconnected') => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    setStatus((prev) => {
      if (prev === nextStatus) {
        return prev;
      }
      if (prev === 'idle' && nextStatus === 'disconnected') {
        return prev;
      }
      return nextStatus;
    });
  }, []);

  const connect = useCallback(() => {
    if (!resolvedUrl) {
      closeConnection('idle');
      setLastError(null);
      return;
    }

    closeConnection('idle');
    setStatus('connecting');
    setLastError(null);

    const shouldUsePolyfill = Boolean(
      options && (options.method && options.method !== 'GET' || options.payload || options.headers)
    );

    const es = shouldUsePolyfill
      ? new SSE(resolvedUrl, options)
      : new EventSource(resolvedUrl, shouldUsePolyfill ? undefined : options);
    eventSourceRef.current = es;

    // Standard open event
    es.onopen = () => {
      console.log('SSE connection opened.');
      reconnectAttemptsRef.current = 0; // Reset attempts on successful connection
      setStatus('connected');
      setLastError(null);
      if (eventListeners.open) {
        eventListeners.open();
      }
    };

    // --- Custom Event Listeners ---

    // Listen for all custom events passed by the consumer
    Object.entries(eventListeners).forEach(([eventName, handler]) => {
      // The 'error' event is special, we handle it separately below
      if (eventName !== 'error' && eventName !== 'open' && eventName !== 'done') {
        es.addEventListener(eventName, handler);
      }
    });

    // Specific handler for the 'done' event to close the connection
    es.addEventListener('done', (e) => {
      if (eventListeners.done) {
        eventListeners.done(e);
      }
      console.log('SSE stream "done" event received. Closing connection.');
      setLastError(null);
      closeConnection('completed');
    });

    // Specific handler for application-level errors sent via the 'error' event
    es.addEventListener('error', (e) => {
      // This is for custom error events, not connection errors
      if (eventListeners.error) {
        let errorData;
        try {
          errorData = JSON.parse(e.data);
        } catch (jsonError) {
          errorData = { error: 'Received an unparsable error event from server.' };
        }
        const emittedError = new Error(errorData.error || 'An unknown error occurred in the stream.');
        setLastError(emittedError);
        eventListeners.error(emittedError);
      }
      console.error('SSE stream "error" event received. Closing connection.');
      // Don't reconnect on application-level errors
      closeConnection('failed');
    });

    // --- Connection Error Handler ---

    // This handles network-level errors (e.g., server down)
    es.onerror = (e) => {
      console.error('SSE connection error:', e);
      closeConnection('disconnected');

      const transientError = new Error('실시간 연결이 일시적으로 끊어졌습니다.');
      setLastError(transientError);

      if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttemptsRef.current++;
        const delay = INITIAL_RECONNECT_DELAY * Math.pow(2, reconnectAttemptsRef.current - 1);
        console.log(`Attempting to reconnect in ${delay}ms (attempt ${reconnectAttemptsRef.current})`);
        setStatus('reconnecting');
        reconnectTimeoutRef.current = setTimeout(connect, delay);
      } else {
        console.error('Max reconnection attempts reached.');
        const finalError = new Error('Connection failed after multiple retries.');
        setLastError(finalError);
        if (eventListeners.error) {
          eventListeners.error(finalError);
        }
        closeConnection('failed');
      }
    };

    if (shouldUsePolyfill && typeof es.stream === 'function') {
      es.stream();
    }

  }, [resolvedUrl, eventListeners, closeConnection, options]);

  useEffect(() => {
    connect();
    return () => {
      closeConnection('idle');
    };
  }, [connect, closeConnection]);

  const reconnect = useCallback(() => {
    reconnectAttemptsRef.current = 0;
    setLastError(null);
    connect();
  }, [connect]);

  return { status, reconnect, error: lastError };
};

export default useEventSource;
