import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';

const useConversationStore = create(
  immer((set, get) => ({
    threads: [],
    messagesByThread: {}, // { [threadId]: [message1, message2] }

    // Room creation flow state
    roomCreationRequest: {
      active: false,
      type: null, // 'SUB' or 'REVIEW'
      parentId: null,
      promptText: '',
    },

    // Generation Settings
    model: 'gpt-4o',
    temperature: 0.7,
    maxTokens: 2048,

    actions: {
      setThreads: (threads) => set({ threads }),

      setSettings: (settings) => set((state) => {
        if (settings.model !== undefined) state.model = settings.model;
        if (settings.temperature !== undefined) state.temperature = settings.temperature;
        if (settings.maxTokens !== undefined) state.maxTokens = settings.maxTokens;
      }),

      addThread: (thread) => set((state) => {
        state.threads.unshift(thread);
      }),

      setMessages: (threadId, messages) => set((state) => {
        state.messagesByThread[threadId] = messages;
      }),

      addMessage: (threadId, message) => set((state) => {
        if (!state.messagesByThread[threadId]) {
          state.messagesByThread[threadId] = [];
        }
        // Avoid adding duplicates
        if (!state.messagesByThread[threadId].find(m => m.id === message.id)) {
            state.messagesByThread[threadId].push(message);
        }
      }),

      appendStreamChunk: (threadId, messageId, chunk) => set((state) => {
        const threadMessages = state.messagesByThread[threadId];
        if (!threadMessages) return;
        const message = threadMessages.find(m => m.id === messageId);
        if (message) {
          message.content += chunk;
        }
      }),

      updateMessage: (threadId, messageId, updatedMessage) => set((state) => {
        const threadMessages = state.messagesByThread[threadId];
        if (!threadMessages) return;
        const messageIndex = threadMessages.findIndex(m => m.id === messageId);
        if (messageIndex !== -1) {
          threadMessages[messageIndex] = updatedMessage;
        }
      }),

      startRoomCreation: (parentId, type, promptText) => {
        console.log('startRoomCreation called:', { parentId, type, promptText });
        set((state) => {
          console.log('Setting roomCreationRequest state:', { parentId, type, promptText });
          state.roomCreationRequest = {
            active: true,
            type,
            parentId,
            promptText,
          };
          console.log('New state after setting:', state.roomCreationRequest);
        });
      },

      clearRoomCreation: () => set((state) => {
        state.roomCreationRequest = {
          active: false,
          type: null,
          parentId: null,
          promptText: '',
        };
      }),

      // Interactive review room creation
      reviewRoomCreation: {
        active: false,
        parentId: null,
        topic: null,
        history: [], // [{role: 'user' | 'assistant', content: '...'}, ...]
      },

      startReviewRoomCreation: (parentId, topic) => set((state) => {
        state.reviewRoomCreation = {
          active: true,
          parentId,
          topic,
          history: [{ role: 'user', content: topic }],
        };
      }),

      addReviewRoomHistory: (message) => set((state) => {
        if (state.reviewRoomCreation.active) {
          state.reviewRoomCreation.history.push(message);
        }
      }),

      clearReviewRoomCreation: () => set((state) => {
        state.reviewRoomCreation = {
          active: false,
          parentId: null,
          topic: null,
          history: [],
        };
      }),
    }
  }))
);

export const useThreads = () => useConversationStore((state) => state.threads);
export const useMessages = (threadId) => {
  const messages = useConversationStore((state) => state.messagesByThread[threadId]);
  return messages || [];
};
// Export individual action functions to avoid object recreation
export const setThreads = (threads) => useConversationStore.getState().actions.setThreads(threads);
export const addThread = (thread) => useConversationStore.getState().actions.addThread(thread);
export const setMessages = (threadId, messages) => useConversationStore.getState().actions.setMessages(threadId, messages);
export const addMessage = (threadId, message) => useConversationStore.getState().actions.addMessage(threadId, message);
export const updateMessage = (threadId, messageId, updatedMessage) => useConversationStore.getState().actions.updateMessage(threadId, messageId, updatedMessage);
export const appendStreamChunk = (threadId, messageId, chunk) => useConversationStore.getState().actions.appendStreamChunk(threadId, messageId, chunk);
export const startRoomCreation = (parentId, type, promptText) => useConversationStore.getState().actions.startRoomCreation(parentId, type, promptText);
export const clearRoomCreation = () => useConversationStore.getState().actions.clearRoomCreation();
export const setSettings = (settings) => useConversationStore.getState().actions.setSettings(settings);
export const useRoomCreationRequest = () => useConversationStore((state) => state.roomCreationRequest);
export const useReviewRoomCreation = () => useConversationStore((state) => state.reviewRoomCreation);
export const startReviewRoomCreation = (parentId, topic) => useConversationStore.getState().actions.startReviewRoomCreation(parentId, topic);
export const addReviewRoomHistory = (message) => useConversationStore.getState().actions.addReviewRoomHistory(message);
export const clearReviewRoomCreation = () => useConversationStore.getState().actions.clearReviewRoomCreation();
export const useGenerationSettings = () => {
  const model = useConversationStore((state) => state.model);
  const temperature = useConversationStore((state) => state.temperature);
  const maxTokens = useConversationStore((state) => state.maxTokens);
  
  return { model, temperature, maxTokens };
};
