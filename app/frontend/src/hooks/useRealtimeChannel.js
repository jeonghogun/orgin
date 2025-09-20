import { useMemo } from 'react';
import useEventSource from './useEventSource';
import { parseRealtimeEvent } from '../utils/realtime';

const DEFAULT_ERROR_MESSAGE = '실시간 스트림 처리 중 문제가 발생했어요. 잠시 후 다시 시도해주세요.';

const useRealtimeChannel = ({
  url,
  events = {},
  parser = parseRealtimeEvent,
  onError,
  sseOptions,
} = {}) => {
  const wrappedHandlers = useMemo(() => {
    const mappedHandlers = {};

    Object.entries(events).forEach(([eventName, handler]) => {
      if (typeof handler !== 'function' || eventName === 'error') {
        return;
      }

      mappedHandlers[eventName] = (event) => {
        const parsed = parser ? parser(event) : event;
        if (parsed == null) {
          return;
        }
        handler(parsed, event);
      };
    });

    const errorHandler = events.error || onError;

    mappedHandlers.error = (eventOrError) => {
      if (typeof errorHandler !== 'function') {
        if (eventOrError instanceof Error) {
          console.error('Realtime channel error without handler:', eventOrError);
        } else {
          console.error('Realtime channel error without handler.', eventOrError);
        }
        return;
      }

      if (eventOrError instanceof Error) {
        errorHandler(eventOrError);
        return;
      }

      const parsed = parser ? parser(eventOrError) : null;
      const message =
        parsed?.payload?.error || parsed?.error || DEFAULT_ERROR_MESSAGE;
      const error = new Error(message);
      if (parsed?.meta) {
        error.meta = parsed.meta;
      }
      errorHandler(error);
    };

    return mappedHandlers;
  }, [events, onError, parser]);

  return useEventSource(url, wrappedHandlers, sseOptions);
};

export default useRealtimeChannel;
