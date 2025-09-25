import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';

const RenameRoomModal = ({ room, isOpen, onClose, onSave }) => {
  const [name, setName] = useState('');

  useEffect(() => {
    if (room) {
      setName(room.name);
    }
  }, [room]);

  if (!isOpen || !room) return null;

  const handleSave = () => {
    if (name.trim()) {
      onSave(name.trim());
    }
  };

  return createPortal(
    <div className="fixed inset-0 bg-black bg-opacity-90 z-[999999] flex justify-center items-center">
      <div className="bg-panel rounded-lg shadow-xl p-6 w-full max-w-md relative z-[9999999]">
        <h2 className="text-xl font-bold mb-4">룸 이름 변경</h2>
        <p className="text-muted mb-4">"{room.name}" 룸의 새로운 이름을 입력하세요.</p>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full px-4 py-3 bg-panel-elev border border-border rounded-input text-body text-text placeholder-muted focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent"
          autoFocus
        />
        <div className="flex justify-end gap-3 mt-6">
          <button onClick={onClose} className="btn-secondary px-4 py-2 rounded-button">
            취소
          </button>
          <button onClick={handleSave} className="btn-primary px-4 py-2 rounded-button">
            저장
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default RenameRoomModal;
