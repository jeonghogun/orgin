export const parseRealtimeEvent = (event) => {
  if (!event || typeof event.data !== 'string') {
    return null;
  }

  const trimmed = event.data.trim();
  if (
    trimmed === '' ||
    trimmed.toLowerCase() === 'keep-alive' ||
    trimmed.toLowerCase() === 'heartbeat' ||
    trimmed === '[heartbeat]' ||
    trimmed.startsWith(':')
  ) {
    return null;
  }

  try {
    return JSON.parse(event.data);
  } catch (error) {
    console.error('Failed to parse realtime payload:', error);
    return null;
  }
};

export const withFallbackMeta = (envelope, extras = {}) => {
  if (!envelope || typeof envelope !== 'object') {
    return { meta: extras };
  }

  const meta = typeof envelope.meta === 'object' && envelope.meta !== null ? envelope.meta : {};
  return { ...envelope, meta: { ...meta, ...extras } };
};
