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
      promptMessageId: null,
    },

    reviewRoomCreation: {
      active: false,
      parentId: null,
      topic: null,
      history: [],
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
            state.messagesByThread[threadId].push({
              content: '',
              status: 'complete',
              meta: {},
              ...message,
            });
        }
      }),

      appendStreamChunk: (threadId, messageId, chunk) => set((state) => {
        const threadMessages = state.messagesByThread[threadId];
        if (!threadMessages) return;
        const message = threadMessages.find(m => m.id === messageId);
        if (message) {
          if (typeof message.content !== 'string') {
            message.content = '';
          }
          message.content += chunk;
          if (!['complete', 'archived', 'error'].includes(message.status)) {
            message.status = 'streaming';
          }
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

      setMessageStatus: (threadId, messageId, status, metaUpdates) => set((state) => {
        const threadMessages = state.messagesByThread[threadId];
        if (!threadMessages) return;
        const message = threadMessages.find((m) => m.id === messageId);
        if (message) {
          message.status = status;
          if (metaUpdates) {
            message.meta = { ...(message.meta || {}), ...metaUpdates };
          }
        }
      }),

      markMessageError: (threadId, messageId, errorMessage, fallbackContent) => set((state) => {
        const threadMessages = state.messagesByThread[threadId];
        if (!threadMessages) return;
        const message = threadMessages.find((m) => m.id === messageId);
        if (message) {
          message.status = 'error';
          message.meta = { ...(message.meta || {}), error: errorMessage };
          if (typeof fallbackContent === 'string') {
            message.content = fallbackContent;
          }
        }
      }),

      startRoomCreation: (parentId, type, promptText, promptMessageId = null) => {
        set((state) => {
          state.roomCreationRequest = {
            active: true,
            type,
            parentId,
            promptText,
            promptMessageId,
          };
        });
      },

      clearRoomCreation: () => set((state) => {
        state.roomCreationRequest = {
          active: false,
          type: null,
          parentId: null,
          promptText: '',
          promptMessageId: null,
        };
      }),

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
export const setMessageStatus = (threadId, messageId, status, metaUpdates) =>
  useConversationStore.getState().actions.setMessageStatus(threadId, messageId, status, metaUpdates);
export const markMessageError = (threadId, messageId, errorMessage, fallbackContent) =>
  useConversationStore.getState().actions.markMessageError(threadId, messageId, errorMessage, fallbackContent);
export const startRoomCreation = (parentId, type, promptText, promptMessageId) =>
  useConversationStore.getState().actions.startRoomCreation(parentId, type, promptText, promptMessageId);
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
