import React, { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

const fetchMessages = async (roomId) => {
  if (!roomId) return [];
  const { data } = await axios.get(`/api/rooms/${roomId}/messages`);
  return data.data || [];
};

const CodeBlock = ({ content, language }) => {
  return (
    <div className="bg-panel-elev border border-border rounded-card p-4 my-3">
      {language && (
        <div className="text-meta text-muted mb-2">{language}</div>
      )}
      <pre className="text-body text-text whitespace-pre-wrap overflow-x-auto">
        <code>{content}</code>
      </pre>
    </div>
  );
};

const FileChip = ({ fileData }) => {
  return (
    <div className="inline-flex items-center gap-2 bg-panel-elev border border-border rounded-button px-3 py-2 my-2">
      <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4 text-muted">
        <path d="M3 2a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V3a1 1 0 0 0-1-1H3zm0 1h10v10H3V3z"/>
        <path d="M5 5a1 1 0 1 1 0 2 1 1 0 0 1 0-2zm0 1a.5.5 0 1 0 0 1 .5.5 0 0 0 0-1z"/>
      </svg>
      <a 
        href={fileData.url} 
        target="_blank" 
        rel="noopener noreferrer"
        className="text-body text-text underline hover:text-accent transition-colors duration-150"
      >
        {fileData.name}
      </a>
      <span className="text-meta text-muted">
        ({(fileData.size / 1024).toFixed(1)} KB)
      </span>
    </div>
  );
};

const ImageMessage = ({ imageData }) => {
  return (
    <div className="my-3">
      <img 
        src={imageData.url} 
        alt={imageData.alt || 'Uploaded image'} 
        className="max-w-full h-auto rounded-card border border-border"
      />
    </div>
  );
};

const Message = ({ message }) => {
  const isUser = message.role === 'user';
  
  const renderContent = () => {
    let content;
    try {
      const parsed = JSON.parse(message.content);
      if (parsed.type === 'file') {
        return <FileChip fileData={parsed} />;
      } else if (parsed.type === 'image') {
        return <ImageMessage imageData={parsed} />;
      } else if (parsed.type === 'code') {
        return <CodeBlock content={parsed.content} language={parsed.language} />;
      } else {
        content = message.content;
      }
    } catch {
      content = message.content;
    }

    // 링크 처리 (파란색 금지, 밑줄만)
    const linkRegex = /\[([^\]]+)\]\(([^)]+)\)/g;
    const processedContent = content.replace(linkRegex, (match, text, url) => {
      return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="underline hover:text-accent transition-colors duration-150">${text}</a>`;
    });

    return (
      <div 
        className="text-body text-text leading-relaxed"
        dangerouslySetInnerHTML={{ __html: processedContent }}
      />
    );
  };

  return (
    <div className={`flex gap-4 p-4 ${isUser ? 'bg-panel' : 'bg-panel-elev'}`}>
      <div className="flex-shrink-0">
        <div className={`w-7 h-7 rounded-full flex items-center justify-center text-white text-meta font-semibold ${
          isUser ? 'bg-accent' : 'bg-panel-elev'
        }`}>
          {isUser ? 'U' : 'A'}
        </div>
      </div>
      <div className="flex-1 min-w-0">
        {renderContent()}
      </div>
    </div>
  );
};

const MessageList = ({ roomId }) => {
  const messagesEndRef = useRef(null);
  const { data: messages = [], isLoading } = useQuery({
    queryKey: ['messages', roomId],
    queryFn: async () => {
      if (!roomId) return [];
      const response = await axios.get(`/api/rooms/${roomId}/messages`);
      return response.data;
    },
    enabled: !!roomId,
    refetchInterval: 2000, // 2초마다 새로고침
  });

  // 새 메시지가 올 때마다 자동으로 맨 아래로 스크롤
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (!roomId) {
    return (
      <div className="flex items-center justify-center h-full text-muted text-body">
        룸을 선택하여 대화를 시작하세요
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-muted">메시지를 불러오는 중...</div>
      </div>
    );
  }

  if (!messages || messages.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="text-muted mb-2">아직 메시지가 없습니다</div>
          <div className="text-meta text-muted">새로운 대화를 시작해보세요</div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {messages.map((message, index) => (
        <div key={message.id || index} className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
          {message.role === 'assistant' && (
            <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center text-white text-sm font-medium">
              A
            </div>
          )}
          
          <div className={`max-w-[70%] ${message.role === 'user' ? 'order-2' : 'order-1'}`}>
            <div className={`p-3 rounded-card ${
              message.role === 'user' 
                ? 'bg-accent text-white' 
                : 'bg-panel-elev border border-border text-text'
            }`}>
              <div className="text-body whitespace-pre-wrap">{message.content}</div>
            </div>
            <div className={`text-meta text-muted mt-1 ${
              message.role === 'user' ? 'text-right' : 'text-left'
            }`}>
              {new Date(message.timestamp || Date.now()).toLocaleTimeString('ko-KR', {
                hour: '2-digit',
                minute: '2-digit'
              })}
            </div>
          </div>

          {message.role === 'user' && (
            <div className="w-8 h-8 rounded-full bg-accent-weak flex items-center justify-center text-white text-sm font-medium order-1">
              U
            </div>
          )}
        </div>
      ))}
      
      {/* 자동 스크롤을 위한 참조 요소 */}
      <div ref={messagesEndRef} />
    </div>
  );
};

export default MessageList;
