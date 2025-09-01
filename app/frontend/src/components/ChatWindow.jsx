import React, { useState, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';

const fetchMessages = async (roomId) => {
  if (!roomId) return [];
  const { data } = await axios.get(`/api/rooms/${roomId}/messages`);
  return data.data || []; // API 응답에서 data 필드 추출
};

const sendMessage = async ({ roomId, content, intent }) => {
  const payload = { content };
  if (intent) {
    payload.intent = intent;
  }
  const { data } = await axios.post(`/api/rooms/${roomId}/messages`, payload);
  // Return the full data object from the API response, which is nested under 'data'
  return data.data;
};

const uploadFile = async ({ roomId, file }) => {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await axios.post(`/api/rooms/${roomId}/upload`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return data;
};

import LoadingSpinner from './common/LoadingSpinner';
import ErrorMessage from './common/ErrorMessage';
import EmptyState from './common/EmptyState';

const SuggestionBubble = ({ suggestion, onConfirm, onDecline }) => {
  return (
    <div className="suggestion-bubble">
      <p>{suggestion}</p>
      <button className="suggestion-button confirm" onClick={onConfirm}>예</button>
      <button className="suggestion-button decline" onClick={onDecline}>아니오</button>
    </div>
  );
};

const FinalReportDisplay = ({ report }) => {
  if (!report) return null;
  return (
    <div className="final-report-display">
      <h3>토론 보고서: {report.topic}</h3>
      <p>{report.executive_summary}</p>
      <h4>주요 관점</h4>
      <ul>
        {Object.entries(report.perspective_summary || {}).map(([persona, summary]) => (
          <li key={persona}><strong>{persona}:</strong> {summary.summary}</li>
        ))}
      </ul>
      <h4>최종 권고</h4>
      <p>{report.recommendation}</p>
    </div>
  );
};

const FileMessage = ({ fileData }) => {
  return (
    <div className="file-message">
      <span className="file-message-icon">📄</span>
      <div>
        <a href={fileData.url} target="_blank" rel="noopener noreferrer" className="file-message-link">
          {fileData.name}
        </a>
        <div className="file-message-details">
          ({(fileData.size / 1024).toFixed(2)} KB)
        </div>
      </div>
    </div>
  );
};

const ErrorNotification = ({ message, onClose }) => {
  if (!message) return null;
  return (
    <div className="error-notification">
      <span>{message}</span>
      <button onClick={onClose} className="error-notification-close">&times;</button>
    </div>
  );
};

const ChatWindow = ({ roomId }) => {
  const queryClient = useQueryClient();
  const [newMessage, setNewMessage] = useState('');
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [activeSuggestion, setActiveSuggestion] = useState(null);
  const [uiError, setUiError] = useState(null);
  const menuRef = useRef(null);
  const fileInputRef = useRef(null);

  const { data: roomData } = useQuery({
    queryKey: ['room', roomId],
    queryFn: () => axios.get(`/api/rooms/${roomId}`).then(res => res.data),
    enabled: !!roomId,
  });

  const { data: finalReport } = useQuery({
    queryKey: ['finalReport', roomId],
    queryFn: () => axios.get(`/api/reviews/${roomId}/report`).then(res => res.data.data),
    enabled: !!roomData && roomData.type === 'review',
  });

  const { data: messages, error, isLoading } = useQuery({
    queryKey: ['messages', roomId],
    queryFn: () => fetchMessages(roomId),
    enabled: !!roomId,
  });

  const messageMutation = useMutation({
    mutationFn: sendMessage,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['messages', roomId] });
      setNewMessage('');
      if (data?.suggestion) {
        setActiveSuggestion(data.suggestion);
      }
    },
    onError: () => {
      setUiError("메시지 전송에 실패했습니다. 잠시 후 다시 시도해주세요.");
    }
  });

  const uploadMutation = useMutation({
    mutationFn: uploadFile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['messages', roomId] });
    },
    onError: (err) => {
      console.error("File upload failed:", err);
      setUiError("파일 업로드에 실패했습니다.");
    }
  });

  const handleSendMessage = (e) => {
    e.preventDefault();
    if (!newMessage.trim()) return;
    messageMutation.mutate({ roomId, content: newMessage });
  };

  const handlePromoteMemoryClick = () => {
    // Send a message with a hidden intent payload
    messageMutation.mutate({
      roomId,
      content: '기억 올리기 프로세스를 시작합니다.', // User-friendly message
      intent: 'start_memory_promotion' // Hidden intent for the backend
    });
    setIsMenuOpen(false);
  };

  const handleSuggestionConfirm = () => {
    messageMutation.mutate({
      roomId,
      content: '방금 나눈 대화에 대해 검토 진행',
      intent: 'review'
    });
    setActiveSuggestion(null);
  };

  const handleUploadClick = () => {
    fileInputRef.current.click();
    setIsMenuOpen(false);
  };

  const handleFileSelect = (event) => {
    const file = event.target.files[0];
    if (file) {
      uploadMutation.mutate({ roomId, file });
    }
  };

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setIsMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [menuRef]);

  const renderMessages = () => {
    if (isLoading) return <LoadingSpinner />;
    if (error) return <ErrorMessage error={error} message="Failed to fetch messages." />;
    if (!messages || messages.length === 0) {
      return <EmptyState message="No messages yet. Send one to start the conversation." />;
    }
    return messages.map((msg, index) => {
      let content;
      try {
        const parsed = JSON.parse(msg.content);
        if (parsed.type === 'file') {
          content = <FileMessage fileData={parsed} />;
        } else {
          content = msg.content;
        }
      } catch {
        content = msg.content;
      }
      return (
        <div key={index} className={`message ${msg.role}`}>
          <strong>{msg.role}:</strong> {content}
        </div>
      );
    });
  };

  const handleExport = async (format) => {
    if (!roomId) return;
    try {
      const response = await axios.get(`/api/rooms/${roomId}/export?format=${format}`, {
        responseType: format === 'markdown' ? 'blob' : 'json',
      });

      if (format === 'markdown') {
        const url = window.URL.createObjectURL(new Blob([response.data]));
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `export_room_${roomId}_${Date.now()}.md`);
        document.body.appendChild(link);
        link.click();
        link.remove();
      } else {
        // For JSON, maybe open in new tab or copy to clipboard
        const jsonString = JSON.stringify(response.data, null, 2);
        const blob = new Blob([jsonString], { type: 'application/json' });
        const url = window.URL.createObjectURL(blob);
        window.open(url, '_blank');
      }
    } catch (err) {
      console.error(`Failed to export as ${format}`, err);
      setUiError(`데이터를 ${format} 형식으로 내보내는 데 실패했습니다.`);
    }
  };

  if (!roomId) {
    return <div className="chat-window-placeholder"><EmptyState message="Select a room to start chatting." /></div>;
  }

  return (
    <div className="chat-window">
      <div className="chat-header">
        <span>Room: {roomId}</span>
      </div>
      <div className="message-list">
        {finalReport && <FinalReportDisplay report={finalReport} />}
        {renderMessages()}
        {activeSuggestion && (
          <SuggestionBubble
            suggestion={activeSuggestion}
            onConfirm={handleSuggestionConfirm}
            onDecline={() => setActiveSuggestion(null)}
          />
        )}
      </div>

      {isMenuOpen && (
        <div ref={menuRef} className="chat-actions-menu">
          <button className="chat-actions-menu-button" onClick={handleUploadClick}>사진 업로드</button>
          <button className="chat-actions-menu-button" onClick={handleUploadClick}>파일 업로드</button>
          <button className="chat-actions-menu-button" onClick={() => handleExport('json')}>내보내기 (JSON)</button>
          <button className="chat-actions-menu-button" onClick={() => handleExport('markdown')}>내보내기 (Markdown)</button>
          <button className="chat-actions-menu-button" onClick={handlePromoteMemoryClick}>기억 올리기</button>
        </div>
      )}

      <form onSubmit={handleSendMessage} className="message-form">
        <input type="file" ref={fileInputRef} onChange={handleFileSelect} style={{ display: 'none' }} />
        <button type="button" onClick={() => setIsMenuOpen(!isMenuOpen)} className="chat-actions-button">
          +
        </button>
        <input
          type="text"
          value={newMessage}
          onChange={(e) => setNewMessage(e.target.value)}
          placeholder="Type your message..."
          disabled={messageMutation.isLoading || uploadMutation.isLoading}
        />
        <button type="submit" disabled={messageMutation.isLoading || uploadMutation.isLoading}>
          {messageMutation.isLoading ? 'Sending...' : 'Send'}
        </button>
      </form>
      <ErrorNotification message={uiError} onClose={() => setUiError(null)} />
    </div>
  );
};

export default ChatWindow;
