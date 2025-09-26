import React, { useState } from 'react';
import { createPortal } from 'react-dom';

const ExportRoomModal = ({ isOpen, onClose, onConfirm }) => {
  const [format, setFormat] = useState('json');
  const [includeInstructions, setIncludeInstructions] = useState(true);

  if (!isOpen) {
    return null;
  }

  const handleConfirmClick = () => {
    onConfirm?.({ format, includeInstructions });
  };

  return createPortal(
    <div className="fixed inset-0 z-[999999] flex items-center justify-center bg-black/80">
      <div className="w-full max-w-md rounded-lg border border-border bg-panel shadow-xl">
        <div className="border-b border-border/60 px-6 py-4">
          <h2 className="text-lg font-semibold text-text">세부 룸 내보내기</h2>
          <p className="mt-1 text-sm text-muted">
            포맷을 선택하고 지침 포함 여부를 확인하세요.
          </p>
        </div>

        <div className="px-6 py-5 space-y-4">
          <div className="space-y-2">
            <p className="text-sm font-semibold text-text">파일 포맷</p>
            <div className="flex items-center gap-3 text-sm text-text">
              <label className="flex items-center gap-2 rounded-md border border-border px-3 py-2 cursor-pointer hover:border-accent/60">
                <input
                  type="radio"
                  name="export-format"
                  value="json"
                  checked={format === 'json'}
                  onChange={() => setFormat('json')}
                  className="text-accent focus:ring-accent"
                />
                JSON
              </label>
              <label className="flex items-center gap-2 rounded-md border border-border px-3 py-2 cursor-pointer hover:border-accent/60">
                <input
                  type="radio"
                  name="export-format"
                  value="markdown"
                  checked={format === 'markdown'}
                  onChange={() => setFormat('markdown')}
                  className="text-accent focus:ring-accent"
                />
                Markdown
              </label>
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-sm font-semibold text-text">추가 옵션</p>
            <label className="flex items-center gap-2 text-sm text-text">
              <input
                type="checkbox"
                checked={includeInstructions}
                onChange={(event) => setIncludeInstructions(event.target.checked)}
                className="text-accent focus:ring-accent"
              />
              지침을 함께 내보내기
            </label>
            <p className="text-xs text-muted">
              지침에는 검토 세션 설정과 참고 맥락이 포함됩니다.
            </p>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-border/60 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-button border border-border px-3 py-2 text-sm text-text hover:bg-panel-elev focus-ring"
          >
            취소
          </button>
          <button
            type="button"
            onClick={handleConfirmClick}
            className="rounded-button bg-accent px-3 py-2 text-sm font-semibold text-white hover:bg-accent-weak focus-ring"
          >
            내보내기
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default ExportRoomModal;

