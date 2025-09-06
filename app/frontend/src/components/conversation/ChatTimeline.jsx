import React, { useEffect, useRef } from 'react';
import MessageCard from './MessageCard';

const ChatTimeline = ({ messages, isLoading, error, onViewHistory }) => {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages.length, messages[messages.length - 1]?.content]);

  if (isLoading) {
    return <div className="text-center p-8">Loading conversation...</div>;
  }
  if (error) {
    return <div className="text-center p-8 text-red-500">Error: {error.message}</div>;
  }

  return (
    <div className="h-full overflow-y-auto space-y-4">
      {messages.map((msg) => (
        <MessageCard key={msg.id} message={msg} onViewHistory={onViewHistory} />
      ))}
      <div ref={scrollRef} />
    </div>
  );
};

export default ChatTimeline;
