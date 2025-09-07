import React, { useState, useRef, useEffect } from 'react';
import { PaperAirplaneIcon, Cog6ToothIcon } from '@heroicons/react/24/solid';
import SettingsPanel from './SettingsPanel';

const Composer = ({ onSendMessage, onFileUpload, isLoading, isUploading }) => {
  const [text, setText] = useState('');
  const [showSettings, setShowSettings] = useState(false);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [text]);

  const handleSend = () => {
    if (text.trim() && !isLoading) {
      onSendMessage(text.trim());
      setText('');
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      onFileUpload(e.target.files[0]);
      // Reset file input
      e.target.value = null;
    }
  };

  return (
    <div>
      {showSettings && <div className="mb-2"><SettingsPanel /></div>}
      <div className="flex items-center space-x-2 p-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg">
        <button
            onClick={() => setShowSettings(!showSettings)}
            className="p-2 rounded-full hover:bg-gray-200 dark:hover:bg-gray-700"
        >
            <Cog6ToothIcon className="h-5 w-5" />
        </button>
        {/* File upload button can be added back here */}
        <textarea
          ref={textareaRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Type a message..."
        className="flex-1 bg-transparent border-none focus:ring-0 resize-none max-h-48 p-2"
        rows={1}
        disabled={isLoading || isUploading}
      />
      <button
        onClick={handleSend}
        disabled={isLoading || isUploading || !text.trim()}
        className="p-2 rounded-full text-white bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 disabled:cursor-not-allowed"
      >
        <PaperAirplaneIcon className="h-5 w-5" />
      </button>
      </div>
    </div>
  );
};

export default Composer;
