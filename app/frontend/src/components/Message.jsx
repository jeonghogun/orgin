import React, { useState } from 'react';
import PropTypes from 'prop-types';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import remarkGfm from 'remark-gfm';
import DiffViewModal from './conversation/DiffViewModal';

const Message = ({ message }) => {
  const [isHovered, setIsHovered] = useState(false);
  const [showDiff, setShowDiff] = useState(false);
  if (!message) {
    return null;
  }

  const isUser = message.role === 'user';

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
  };

  const Avatar = ({ role }) => (
    <div className={`w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-white text-sm font-medium ${isUser ? 'bg-accent-weak' : 'bg-accent'}`}>
      {isUser ? 'U' : 'A'}
    </div>
  );

  const CodeBlock = ({ node, inline, className, children, ...props }) => {
    const match = /language-(\w+)/.exec(className || '');
    const lang = match ? match[1] : 'text';
    return !inline ? (
      <div className="relative my-2 rounded-md bg-[#2d2d2d]">
        <div className="flex items-center justify-between px-4 py-1 bg-gray-700 text-xs text-gray-300 rounded-t-md">
          <span>{lang}</span>
          <button
            onClick={() => navigator.clipboard.writeText(String(children))}
            className="p-1 rounded hover:bg-gray-600"
          >
            Copy
          </button>
        </div>
        <SyntaxHighlighter
          style={vscDarkPlus}
          language={lang}
          PreTag="div"
          {...props}
        >
          {String(children).replace(/\n$/, '')}
        </SyntaxHighlighter>
      </div>
    ) : (
      <code className="bg-gray-700 text-red-400 px-1 rounded" {...props}>
        {children}
      </code>
    );
  };

  return (
    <div 
      className={`flex gap-3 items-start relative ${isUser ? 'justify-end' : 'justify-start'}`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {!isUser && <Avatar role="assistant" />}
      <div className={`max-w-[70%] group`}>
        <div className={`p-3 rounded-card relative ${
          isUser 
            ? 'bg-accent text-white' 
            : 'bg-panel-elev border border-border text-text'
        }`}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            className="prose prose-sm dark:prose-invert max-w-none"
            components={{ code: CodeBlock }}
          >
            {message.content || ''}
          </ReactMarkdown>
          {isHovered && (
            <div className="absolute -top-3 -right-3 flex gap-1">
              <button
                onClick={() => setShowDiff(true)}
                className="p-1 bg-gray-700 rounded-full text-white hover:bg-gray-600 transition-opacity"
                title="View edit history"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              </button>
              <button
                onClick={handleCopy}
                className="p-1 bg-gray-700 rounded-full text-white hover:bg-gray-600 transition-opacity"
                title="Copy message"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
              </button>
            </div>
          )}
        </div>
        <div className={`text-meta text-muted mt-1 ${isUser ? 'text-right' : 'text-left'}`}>
          {new Date((message.timestamp ?? Date.now() / 1000) * 1000).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
      {isUser && <Avatar role="user" />}
      {showDiff && <DiffViewModal messageId={message.message_id} onClose={() => setShowDiff(false)} />}
    </div>
  );
};

Message.propTypes = {
  message: PropTypes.shape({
    id: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    message_id: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    role: PropTypes.string,
    content: PropTypes.string,
    timestamp: PropTypes.number,
    meta: PropTypes.object,
  }),
};

export default Message;
