import { useEffect, useCallback } from 'react';

const useKeyboardShortcuts = (shortcuts) => {
  const handleKeyDown = useCallback((event) => {
    // Ctrl/Cmd + 키 조합 확인
    const isCtrlOrCmd = event.ctrlKey || event.metaKey;
    const isShift = event.shiftKey;
    const isAlt = event.altKey;
    
    // 단축키 매핑
    const keyMap = {
      // 기본 단축키
      'Ctrl+N': isCtrlOrCmd && event.key === 'n',
      'Ctrl+S': isCtrlOrCmd && event.key === 's',
      'Ctrl+Z': isCtrlOrCmd && event.key === 'z',
      'Ctrl+Y': isCtrlOrCmd && event.key === 'y',
      'Ctrl+F': isCtrlOrCmd && event.key === 'f',
      'Ctrl+A': isCtrlOrCmd && event.key === 'a',
      'Ctrl+C': isCtrlOrCmd && event.key === 'c',
      'Ctrl+V': isCtrlOrCmd && event.key === 'v',
      'Ctrl+X': isCtrlOrCmd && event.key === 'x',
      'Ctrl+K': isCtrlOrCmd && event.key === 'k',
      
      // 커스텀 단축키
      'Ctrl+Enter': isCtrlOrCmd && event.key === 'Enter',
      'Ctrl+Shift+Enter': isCtrlOrCmd && isShift && event.key === 'Enter',
      'Ctrl+Space': isCtrlOrCmd && event.key === ' ',
      'Ctrl+Shift+S': isCtrlOrCmd && isShift && event.key === 's',
      'Ctrl+Shift+N': isCtrlOrCmd && isShift && event.key === 'n',
      'Ctrl+Shift+M': isCtrlOrCmd && isShift && event.key === 'm',
      'Ctrl+Shift+A': isCtrlOrCmd && isShift && event.key === 'a',
      
      // 기능키
      'F1': event.key === 'F1',
      'F2': event.key === 'F2',
      'F3': event.key === 'F3',
      'F4': event.key === 'F4',
      'F5': event.key === 'F5',
      'F6': event.key === 'F6',
      'F7': event.key === 'F7',
      'F8': event.key === 'F8',
      'F9': event.key === 'F9',
      'F10': event.key === 'F10',
      'F11': event.key === 'F11',
      'F12': event.key === 'F12',
      
      // 방향키
      'ArrowUp': event.key === 'ArrowUp',
      'ArrowDown': event.key === 'ArrowDown',
      'ArrowLeft': event.key === 'ArrowLeft',
      'ArrowRight': event.key === 'ArrowRight',
      
      // 기타 키
      'Escape': event.key === 'Escape',
      'Tab': event.key === 'Tab',
      'Enter': event.key === 'Enter',
      'Backspace': event.key === 'Backspace',
      'Delete': event.key === 'Delete',
    };
    
    // 매칭되는 단축키 찾기
    for (const [shortcut, handler] of Object.entries(shortcuts)) {
      if (keyMap[shortcut]) {
        event.preventDefault();
        handler(event);
        break;
      }
    }
  }, [shortcuts]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleKeyDown]);
};

export default useKeyboardShortcuts;
