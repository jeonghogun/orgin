import { useEffect, useRef, useCallback, useState, useMemo } from 'react';
import { SSE } from 'sse.js';
import { resolveApiUrl } from '../lib/apiClient';

const MAX_RECONNECT_ATTEMPTS = 3;
const INITIAL_RECONNECT_DELAY = 1000;

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
  const resolvedUrl = useMemo(() => (url ? resolveApiUrl(url) : null), [url]);

  const closeConnection = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    setStatus((prev) => (prev === 'idle' ? prev : 'disconnected'));
  }, []);

  const connect = useCallback(() => {
    if (!resolvedUrl) {
      closeConnection();
      setStatus('idle');
      return;
    }

    closeConnection();

    setStatus('connecting');

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
      closeConnection();
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
        eventListeners.error(new Error(errorData.error || 'An unknown error occurred in the stream.'));
      }
      console.error('SSE stream "error" event received. Closing connection.');
      closeConnection();
    });

    // --- Connection Error Handler ---

    // This handles network-level errors (e.g., server down)
    es.onerror = (e) => {
      console.error('SSE connection error:', e);
      es.close(); // Ensure the errored connection is closed

      // Don't reconnect if the error was a custom one we already handled
      if (!eventSourceRef.current) {
          return;
      }

      if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttemptsRef.current++;
        const delay = INITIAL_RECONNECT_DELAY * Math.pow(2, reconnectAttemptsRef.current - 1);
        console.log(`Attempting to reconnect in ${delay}ms (attempt ${reconnectAttemptsRef.current})`);
        setStatus('reconnecting');
        reconnectTimeoutRef.current = setTimeout(connect, delay);
      } else {
        console.error('Max reconnection attempts reached.');
        if (eventListeners.error) {
          eventListeners.error(new Error('Connection failed after multiple retries.'));
        }
        setStatus('failed');
        closeConnection();
      }
    };

    if (shouldUsePolyfill && typeof es.stream === 'function') {
      es.stream();
    }

  }, [resolvedUrl, eventListeners, closeConnection, options]);

  useEffect(() => {
    connect();
    return () => {
      closeConnection();
    };
  }, [connect, closeConnection]);

  // No return value needed, the hook manages the connection internally.
  return { status };
};

export default useEventSource;
