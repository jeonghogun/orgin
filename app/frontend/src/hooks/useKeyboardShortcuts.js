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

// 기본 단축키 설정
export const defaultShortcuts = {
  // 새 룸 생성
  'Ctrl+N': (event) => {
    console.log('새 룸 생성');
    // TODO: 새 룸 생성 로직
  },
  
  // 저장
  'Ctrl+S': (event) => {
    console.log('저장');
    // TODO: 저장 로직
  },
  
  // 실행 취소
  'Ctrl+Z': (event) => {
    console.log('실행 취소');
    // TODO: 실행 취소 로직
  },
  
  // 다시 실행
  'Ctrl+Y': (event) => {
    console.log('다시 실행');
    // TODO: 다시 실행 로직
  },
  
  // 검색
  'Ctrl+F': (event) => {
    console.log('검색');
    // TODO: 검색 로직
  },
  
  // 전체 선택
  'Ctrl+A': (event) => {
    console.log('전체 선택');
    // TODO: 전체 선택 로직
  },
  
  // 복사
  'Ctrl+C': (event) => {
    console.log('복사');
    // TODO: 복사 로직
  },
  
  // 붙여넣기
  'Ctrl+V': (event) => {
    console.log('붙여넣기');
    // TODO: 붙여넣기 로직
  },
  
  // 잘라내기
  'Ctrl+X': (event) => {
    console.log('잘라내기');
    // TODO: 잘라내기 로직
  },
  
  // 메시지 전송 (Ctrl+Enter)
  'Ctrl+Enter': (event) => {
    console.log('메시지 전송');
    // TODO: 메시지 전송 로직
  },
  
  // 새 줄 (Ctrl+Shift+Enter)
  'Ctrl+Shift+Enter': (event) => {
    console.log('새 줄');
    // TODO: 새 줄 로직
  },
  
  // 메트릭 대시보드 (F1)
  'F1': (event) => {
    console.log('메트릭 대시보드');
    // TODO: 메트릭 대시보드 열기
  },
  
  // 관리자 페이지 (F2)
  'F2': (event) => {
    console.log('관리자 페이지');
    // TODO: 관리자 페이지 열기
  },
  
  // 도움말 (F1)
  'F1': (event) => {
    console.log('도움말');
    // TODO: 도움말 열기
  },
  
  // 새로고침 (F5)
  'F5': (event) => {
    console.log('새로고침');
    // TODO: 새로고침 로직
  },
  
  // 전체화면 (F11)
  'F11': (event) => {
    console.log('전체화면');
    // TODO: 전체화면 토글
  },
  
  // 취소 (Escape)
  'Escape': (event) => {
    console.log('취소');
    // TODO: 취소 로직
  },
};

export default useKeyboardShortcuts;
