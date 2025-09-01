import React, { useState, useRef, useEffect } from 'react';

const SplitView = ({ 
  leftPanel, 
  rightPanel, 
  defaultRatio = 0.4, 
  minLeftWidth = 360,
  minRightWidth = 360 
}) => {
  const [leftWidth, setLeftWidth] = useState(defaultRatio);
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef(null);
  const handleRef = useRef(null);

  const handleMouseDown = (e) => {
    e.preventDefault();
    setIsDragging(true);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  const handleMouseMove = (e) => {
    if (!isDragging || !containerRef.current) return;

    const containerRect = containerRef.current.getBoundingClientRect();
    const containerWidth = containerRect.width;
    const newLeftWidth = (e.clientX - containerRect.left) / containerWidth;

    // 최소/최대 너비 제한
    const minRatio = minLeftWidth / containerWidth;
    const maxRatio = 1 - (minRightWidth / containerWidth);
    const clampedWidth = Math.max(minRatio, Math.min(maxRatio, newLeftWidth));

    setLeftWidth(clampedWidth);
  };

  const handleMouseUp = () => {
    setIsDragging(false);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  };

  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDragging]);

  return (
    <div 
      ref={containerRef}
      className="flex h-full relative"
      style={{ cursor: isDragging ? 'col-resize' : 'default' }}
    >
      {/* 좌측 패널 */}
      <div 
        className="flex-shrink-0 overflow-hidden"
        style={{ width: `${leftWidth * 100}%` }}
      >
        {leftPanel}
      </div>

      {/* 분할 핸들 */}
      <div
        ref={handleRef}
        className="w-1.5 bg-border hover:bg-accent-weak cursor-col-resize transition-colors duration-150 flex-shrink-0"
        onMouseDown={handleMouseDown}
      />

      {/* 우측 패널 */}
      <div 
        className="flex-1 overflow-hidden"
        style={{ width: `${(1 - leftWidth) * 100}%` }}
      >
        {rightPanel}
      </div>
    </div>
  );
};

export default SplitView;
