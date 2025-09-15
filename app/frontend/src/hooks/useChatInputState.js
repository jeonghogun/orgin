import { useReducer, useCallback } from 'react';

// Action Types
const Action = {
  START_SUB_ROOM_CREATION: 'START_SUB_ROOM_CREATION',
  START_REVIEW_CREATION: 'START_REVIEW_CREATION',
  UPDATE_INPUT: 'UPDATE_INPUT',
  SUBMIT: 'SUBMIT',
  RESET: 'RESET',
};

// Initial State
const initialState = {
  mode: 'default', // 'default', 'creating_sub_room', 'creating_review'
  inputValue: '',
  placeholder: '무엇이든 물어보세요...',
  parentId: null, // For room creation context
};

// Reducer Function
function reducer(state, action) {
  switch (action.type) {
    case Action.START_SUB_ROOM_CREATION:
      return {
        ...state,
        mode: 'creating_sub_room',
        placeholder: '새 세부룸의 이름을 입력하세요:',
        parentId: action.payload.parentId,
      };
    case Action.START_REVIEW_CREATION:
      return {
        ...state,
        mode: 'creating_review',
        placeholder: '어떤 주제로 검토룸을 만들까요?',
        parentId: action.payload.parentId,
      };
    case Action.UPDATE_INPUT:
      return { ...state, inputValue: action.payload };
    case Action.SUBMIT:
    case Action.RESET:
      return { ...initialState }; // Reset to default after submission or cancellation
    default:
      return state;
  }
}

// The Custom Hook
export function useChatInputState() {
  const [state, dispatch] = useReducer(reducer, initialState);

  const startSubRoomCreation = useCallback((parentId) => {
    dispatch({ type: Action.START_SUB_ROOM_CREATION, payload: { parentId } });
  }, []);

  const startReviewCreation = useCallback((parentId) => {
    dispatch({ type: Action.START_REVIEW_CREATION, payload: { parentId } });
  }, []);

  const handleInputChange = useCallback((e) => {
    dispatch({ type: Action.UPDATE_INPUT, payload: e.target.value });
  }, []);

  const resetState = useCallback(() => {
    dispatch({ type: Action.RESET });
  }, []);

  // The component is now responsible for the submit logic
  return {
    ...state,
    startSubRoomCreation,
    startReviewCreation,
    handleInputChange,
    resetState,
    dispatch, // Pass dispatch for more complex state changes if needed
  };
}
