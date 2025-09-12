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

      startRoomCreation: (parentId, type, promptText) => set((state) => {
        state.roomCreationRequest = {
          active: true,
          type,
          parentId,
          promptText,
        };
      }),

      clearRoomCreation: () => set((state) => {
        state.roomCreationRequest = {
          active: false,
          type: null,
          parentId: null,
          promptText: '',
        };
      }),
    }
  }))
);

export const useThreads = () => useConversationStore((state) => state.threads);
export const useMessages = (threadId) => useConversationStore((state) => state.messagesByThread[threadId] || []);
export const useConversationActions = () => useConversationStore((state) => state.actions);
export const useRoomCreationRequest = () => useConversationStore((state) => state.roomCreationRequest);
export const useGenerationSettings = () => useConversationStore((state) => ({
    model: state.model,
    temperature: state.temperature,
    maxTokens: state.maxTokens,
}));
