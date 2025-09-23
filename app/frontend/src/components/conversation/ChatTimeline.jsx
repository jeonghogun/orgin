import React, { useEffect, useRef } from 'react';
import PropTypes from 'prop-types';
import MessageCard from './MessageCard';

const ChatTimeline = ({ messages, isLoading, error, onRetry }) => {
  const scrollRef = useRef(null);
  const safeMessages = Array.isArray(messages) ? messages : [];

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [safeMessages.length, safeMessages[safeMessages.length - 1]?.content]);

  if (isLoading) {
    return <div className="text-center p-8">Loading conversation...</div>;
  }
  if (error) {
    return <div className="text-center p-8 text-red-500">Error: {error.message}</div>;
  }

  return (
    <div className="h-full overflow-y-auto space-y-4">
      {safeMessages.map((msg) => (
        <MessageCard key={msg.id} message={msg} onRetry={onRetry} />
      ))}
      <div ref={scrollRef} />
    </div>
  );
};

ChatTimeline.propTypes = {
  messages: PropTypes.arrayOf(PropTypes.object),
  isLoading: PropTypes.bool,
  error: PropTypes.shape({ message: PropTypes.string }),
  onRetry: PropTypes.func,
};

export default ChatTimeline;
