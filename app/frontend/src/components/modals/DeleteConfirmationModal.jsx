import React from 'react';

const DeleteConfirmationModal = ({ room, isOpen, onClose, onConfirm }) => {
  if (!isOpen || !room) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center">
      <div className="bg-panel rounded-lg shadow-xl p-6 w-full max-w-md">
        <h2 className="text-xl font-bold mb-4 text-danger">룸 삭제 확인</h2>
        <p className="text-muted mb-4">
          정말로 "{room.name}" 룸을 삭제하시겠습니까? 이 룸과 관련된 모든 하위 룸 및 데이터가 영구적으로 삭제됩니다. 이 작업은 되돌릴 수 없습니다.
        </p>
        <div className="flex justify-end gap-3 mt-6">
          <button onClick={onClose} className="btn-secondary px-4 py-2 rounded-button">
            취소
          </button>
          <button onClick={onConfirm} className="btn-danger px-4 py-2 rounded-button">
            삭제 확인
          </button>
        </div>
      </div>
    </div>
  );
};

export default DeleteConfirmationModal;
