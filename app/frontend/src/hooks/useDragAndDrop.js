import { useState, useCallback, useRef } from 'react';

const useDragAndDrop = (options = {}) => {
  const {
    onDrop,
    onDragEnter,
    onDragLeave,
    onDragOver,
    accept = '*',
    multiple = false,
    disabled = false
  } = options;

  const [isDragOver, setIsDragOver] = useState(false);
  const [dragCounter, setDragCounter] = useState(0);
  const dropRef = useRef(null);

  const handleDragEnter = useCallback((event) => {
    event.preventDefault();
    event.stopPropagation();
    
    if (disabled) return;
    
    setDragCounter(prev => prev + 1);
    
    if (event.dataTransfer.items && event.dataTransfer.items.length > 0) {
      setIsDragOver(true);
      onDragEnter?.(event);
    }
  }, [disabled, onDragEnter]);

  const handleDragLeave = useCallback((event) => {
    event.preventDefault();
    event.stopPropagation();
    
    if (disabled) return;
    
    setDragCounter(prev => prev - 1);
    
    if (dragCounter <= 1) {
      setIsDragOver(false);
      onDragLeave?.(event);
    }
  }, [disabled, onDragLeave, dragCounter]);

  const handleDragOver = useCallback((event) => {
    event.preventDefault();
    event.stopPropagation();
    
    if (disabled) return;
    
    event.dataTransfer.dropEffect = 'copy';
    onDragOver?.(event);
  }, [disabled, onDragOver]);

  const handleDrop = useCallback((event) => {
    event.preventDefault();
    event.stopPropagation();
    
    if (disabled) return;
    
    setIsDragOver(false);
    setDragCounter(0);
    
    const files = Array.from(event.dataTransfer.files);
    const items = Array.from(event.dataTransfer.items);
    
    // 파일 타입 검증
    const validFiles = files.filter(file => {
      if (accept === '*') return true;
      
      const acceptedTypes = accept.split(',').map(type => type.trim());
      return acceptedTypes.some(type => {
        if (type.startsWith('.')) {
          // 파일 확장자 검사
          return file.name.toLowerCase().endsWith(type.toLowerCase());
        } else {
          // MIME 타입 검사
          return file.type.match(new RegExp(type.replace('*', '.*')));
        }
      });
    });
    
    if (validFiles.length > 0) {
      const filesToProcess = multiple ? validFiles : [validFiles[0]];
      onDrop?.(filesToProcess, event);
    }
  }, [disabled, onDrop, accept, multiple]);

  const dragHandlers = {
    onDragEnter: handleDragEnter,
    onDragLeave: handleDragLeave,
    onDragOver: handleDragOver,
    onDrop: handleDrop
  };

  return {
    isDragOver,
    dragHandlers,
    dropRef
  };
};

// 파일 업로드 전용 훅
export const useFileUpload = (options = {}) => {
  const {
    onUpload,
    accept = 'image/*,text/*,.pdf,.doc,.docx',
    multiple = true,
    maxSize = 10 * 1024 * 1024, // 10MB
    disabled = false
  } = options;

  const handleDrop = useCallback((files, event) => {
    const validFiles = files.filter(file => {
      // 파일 크기 검증
      if (file.size > maxSize) {
        console.warn(`File ${file.name} is too large (${file.size} bytes)`);
        return false;
      }
      return true;
    });

    if (validFiles.length > 0) {
      onUpload?.(validFiles, event);
    }
  }, [onUpload, maxSize]);

  return useDragAndDrop({
    onDrop: handleDrop,
    accept,
    multiple,
    disabled
  });
};

// 이미지 업로드 전용 훅
export const useImageUpload = (options = {}) => {
  const {
    onUpload,
    multiple = true,
    maxSize = 5 * 1024 * 1024, // 5MB
    accept = 'image/*',
    disabled = false
  } = options;

  return useFileUpload({
    onUpload,
    accept,
    multiple,
    maxSize,
    disabled
  });
};

// 문서 업로드 전용 훅
export const useDocumentUpload = (options = {}) => {
  const {
    onUpload,
    multiple = true,
    maxSize = 20 * 1024 * 1024, // 20MB
    accept = '.pdf,.doc,.docx,.txt,.md',
    disabled = false
  } = options;

  return useFileUpload({
    onUpload,
    accept,
    multiple,
    maxSize,
    disabled
  });
};

export default useDragAndDrop;
