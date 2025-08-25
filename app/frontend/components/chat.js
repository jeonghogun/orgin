/**
 * Chat Component - Main chat functionality
 */
class ChatComponent {
    constructor() {
        this.messagesContainer = document.getElementById('messages');
        this.messageInput = document.getElementById('message-input');
        this.sendButton = document.getElementById('send-button');
        this.currentRoomId = null;
        this.isProcessing = false;
        
        this.initializeEventListeners();
    }
    
    initializeEventListeners() {
        this.sendButton.addEventListener('click', () => this.sendMessage());
        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
    }
    
    setRoomId(roomId) {
        this.currentRoomId = roomId;
        this.loadMessages();
    }
    
    async sendMessage() {
        if (!this.currentRoomId || this.isProcessing) return;
        
        const content = this.messageInput.value.trim();
        if (!content) return;
        
        this.isProcessing = true;
        this.sendButton.disabled = true;
        
        try {
            // Add user message to UI immediately
            this.addMessage('user', content);
            this.messageInput.value = '';
            
            // Check if this is a review command
            if (this.isReviewCommand(content)) {
                await this.handleReviewCommand(content);
            } else {
                // Send to AI for response
                await this.sendToAI(content);
            }
        } catch (error) {
            console.error('Error sending message:', error);
            this.addErrorMessage('메시지 전송에 실패했습니다.');
        } finally {
            this.isProcessing = false;
            this.sendButton.disabled = false;
        }
    }
    
    isReviewCommand(content) {
        const reviewKeywords = ['검토', '리뷰', '토론', '/review'];
        return reviewKeywords.some(keyword => content.includes(keyword));
    }
    
    async handleReviewCommand(content) {
        try {
            const response = await this.apiCall(`/api/rooms/${this.currentRoomId}/reviews`, {
                method: 'POST',
                body: JSON.stringify({
                    topic: content,
                    rounds: this.getDefaultRounds()
                })
            });
            
            if (response.review_id) {
                this.addSystemMessage('검토를 시작하고 있습니다...');
                await this.startReview(response.review_id);
            }
        } catch (error) {
            console.error('Review creation failed:', error);
            this.addErrorMessage('검토 시작에 실패했습니다.');
        }
    }
    
    getDefaultRounds() {
        return [
            {
                round_number: 1,
                mode: "divergent",
                instruction: "주어진 토픽에 대해 다양한 시각에서 분석해라",
                panel_personas: [
                    { name: "Critic", provider: "openai" },
                    { name: "Optimist", provider: "openai" },
                    { name: "Synthesizer", provider: "openai" }
                ]
            },
            {
                round_number: 2,
                mode: "convergent",
                instruction: "앞선 분석들을 종합해 결론을 요약해라",
                panel_personas: [
                    { name: "Consolidator", provider: "openai" }
                ]
            }
        ];
    }
    
    async startReview(reviewId) {
        try {
            await this.apiCall(`/api/reviews/${reviewId}/generate`, { method: 'POST' });
            window.reviewPanel.openReviewPanel(reviewId);
        } catch (error) {
            console.error('Review generation failed:', error);
            this.addErrorMessage('검토 생성에 실패했습니다.');
        }
    }
    
    async sendToAI(content) {
        try {
            const response = await this.apiCall(`/api/rooms/${this.currentRoomId}/messages`, {
                method: 'POST',
                body: JSON.stringify({ content })
            });
            
            // Handle response structure: {data: {ai_response: {...}}, error: false, message: "..."}
            const aiResponse = response.data?.ai_response;
            if (aiResponse) {
                // Extract content from ai_response object
                const aiContent = aiResponse.content || aiResponse;
                this.addMessage('ai', aiContent);
            }
        } catch (error) {
            console.error('AI response failed:', error);
            this.addErrorMessage('AI 응답을 받지 못했습니다.');
        }
    }
    
    addMessage(role, content, timestamp = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        
        const timeStr = timestamp || new Date().toLocaleTimeString();
        const roleText = role === 'user' ? '사용자' : 'AI';
        
        messageDiv.innerHTML = `
            <div class="message-header">
                <span class="role">${roleText}</span>
                <span class="timestamp">${timeStr}</span>
            </div>
            <div class="message-content">${content}</div>
        `;
        
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    addSystemMessage(content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message system';
        messageDiv.innerHTML = `<div class="system-content">${content}</div>`;
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    addErrorMessage(content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message error';
        messageDiv.innerHTML = `<div class="error-content">❌ ${content}</div>`;
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    async loadMessages() {
        if (!this.currentRoomId) return;
        
        try {
            const response = await this.apiCall(`/api/rooms/${this.currentRoomId}/messages`);
            this.messagesContainer.innerHTML = '';
            
            // Handle response structure: {data: [...], error: false, message: "..."}
            const messages = response.data || [];
            
            if (Array.isArray(messages)) {
                messages.forEach(msg => {
                    const content = msg.content || msg;
                    const timestamp = msg.timestamp ? new Date(msg.timestamp * 1000).toLocaleTimeString() : null;
                    this.addMessage(msg.role || 'user', content, timestamp);
                });
            } else {
                console.warn('Messages is not an array:', messages);
            }
        } catch (error) {
            console.error('Failed to load messages:', error);
        }
    }
    
    scrollToBottom() {
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }
    
    async apiCall(endpoint, options = {}) {
        const token = localStorage.getItem('idToken');
        const headers = {
            'Content-Type': 'application/json',
            ...(token && { 'Authorization': `Bearer ${token}` }),
            ...options.headers
        };
        
        const response = await fetch(endpoint, {
            ...options,
            headers
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(`HTTP error ${response.status}: ${JSON.stringify(errorData)}`);
        }
        
        return await response.json();
    }
}

// Export for global use
window.ChatComponent = ChatComponent;

