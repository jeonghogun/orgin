/**
 * Chat Component - Main chat functionality
 */
class ChatComponent {
    constructor() {
        this.messagesContainer = document.getElementById('messages');
        this.messageInput = document.getElementById('message-input');
        this.sendButton = document.getElementById('send-button');
        this.roomListContainer = document.getElementById('room-list');
        this.currentRoomId = null;
        this.isProcessing = false;
        
        this.initializeEventListeners();
    }

    async renderRoomList() {
        try {
            const response = await this.apiCall('/api/rooms');
            const rooms = response.data || [];

            const mainRooms = rooms.filter(r => r.type === 'main');
            const subRoomsByParent = rooms.filter(r => r.type === 'sub').reduce((acc, r) => {
                if (!acc[r.parent_id]) acc[r.parent_id] = [];
                acc[r.parent_id].push(r);
                return acc;
            }, {});

            let html = '<ul>';
            mainRooms.forEach(main => {
                html += `<li class="room-item main-room" data-room-id="${main.room_id}" data-room-type="${main.type}"><span>${main.name}</span>`;
                const children = subRoomsByParent[main.room_id] || [];
                if (children.length > 0) {
                    html += '<ul class="sub-room-list">';
                    children.forEach(sub => {
                        html += `<li class="room-item sub-room" data-room-id="${sub.room_id}" data-room-type="${sub.type}"><span>${sub.name}</span></li>`;
                    });
                    html += '</ul>';
                }
                html += '</li>';
            });
            html += '</ul>';
            this.roomListContainer.innerHTML = html;
        } catch (error) {
            console.error('Failed to render room list:', error);
            this.roomListContainer.innerHTML = '<p class="error">Could not load rooms.</p>';
        }
    }
    
    initializeEventListeners() {
        this.sendButton.addEventListener('click', () => this.sendMessage());
        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        this.roomListContainer.addEventListener('click', (e) => {
            const roomItem = e.target.closest('.room-item');
            if (roomItem) {
                const roomId = roomItem.dataset.roomId;
                const roomType = roomItem.dataset.roomType;
                this.selectRoom(roomId, roomType);
            }
        });

        document.getElementById('start-review-btn').addEventListener('click', () => this.promptForReview());
    }

    async initialize() {
        await this.renderRoomList();
        const rooms = await this.apiCall('/api/rooms').then(res => res.data || []);
        const mainRoom = rooms.find(r => r.type === 'main');

        if (!mainRoom) {
            try {
                const newMainRoom = await this.apiCall('/api/rooms', {
                    method: 'POST',
                    body: JSON.stringify({ name: 'Main Room', type: 'main' })
                });
                await this.renderRoomList();
                this.selectRoom(newMainRoom.room_id, newMainRoom.type);
            } catch (error) {
                this.addErrorMessage("Could not initialize main room.");
            }
        } else {
            this.selectRoom(mainRoom.room_id, mainRoom.type);
        }
    }

    selectRoom(roomId, roomType) {
        this.currentRoomId = roomId;

        document.querySelectorAll('.room-item').forEach(item => item.classList.remove('active'));
        const roomElement = this.roomListContainer.querySelector(`[data-room-id="${roomId}"]`);
        if (roomElement) roomElement.classList.add('active');

        this.messagesContainer.innerHTML = '';
        this.addSystemMessage(`Entered room: ${roomElement ? roomElement.textContent.trim() : roomId}`);
        this.loadMessages();

        const startReviewBtn = document.getElementById('start-review-btn');
        startReviewBtn.style.display = (roomType === 'sub') ? 'block' : 'none';
    }
    
    async sendMessage() {
        if (!this.currentRoomId || this.isProcessing) return;
        const content = this.messageInput.value.trim();
        if (!content) return;
        
        this.isProcessing = true;
        this.sendButton.disabled = true;
        
        try {
            this.addMessage('user', content);
            this.messageInput.value = '';
            await this.sendToAI(content);
        } catch (error) {
            this.addErrorMessage('메시지 전송에 실패했습니다.');
        } finally {
            this.isProcessing = false;
            this.sendButton.disabled = false;
        }
    }

    async promptForReview() {
        const topic = prompt("Enter the review topic:", "The future of AI");
        if (!topic) return;
        const instruction = prompt("Enter the initial instruction for the AI panel:", "Analyze the pros and cons.");
        if (!instruction) return;

        await this.handleReviewCommand(topic, instruction);
    }
    
    async handleReviewCommand(topic, instruction) {
        if (!this.currentRoomId) {
            this.addErrorMessage("Please select a sub-room to start a review.");
            return;
        }
        try {
            const response = await this.apiCall(`/api/rooms/${this.currentRoomId}/reviews`, {
                method: 'POST',
                body: JSON.stringify({ topic, instruction })
            });
            
            if (response.review_id) {
                this.addSystemMessage('Review process initiated...');
                await this.startReview(response.review_id);
            }
        } catch (error) {
            this.addErrorMessage('Failed to start review.');
        }
    }
    
    async startReview(reviewId) {
        try {
            await this.apiCall(`/api/reviews/${reviewId}/generate`, { method: 'POST' });
            window.reviewPanel.openReviewPanel(reviewId);
        } catch (error) {
            this.addErrorMessage('Failed to generate review.');
        }
    }
    
    async sendToAI(content) {
        try {
            const response = await this.apiCall(`/api/rooms/${this.currentRoomId}/messages`, {
                method: 'POST',
                body: JSON.stringify({ content })
            });
            
            const aiResponse = response.data?.ai_response;
            if (aiResponse) {
                this.addMessage('ai', aiResponse.content || aiResponse);
            }
        } catch (error) {
            this.addErrorMessage('AI 응답을 받지 못했습니다.');
        }
    }
    
    addMessage(role, content, timestamp = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        const timeStr = timestamp || new Date().toLocaleTimeString();
        const roleText = role === 'user' ? 'You' : 'AI';
        
        messageDiv.innerHTML = `
            <div class="message-header"><span class="role">${roleText}</span><span class="timestamp">${timeStr}</span></div>
            <div class="message-content">${content}</div>`;
        
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
            const messages = response.data || [];
            
            if (Array.isArray(messages)) {
                messages.forEach(msg => {
                    const timestamp = msg.timestamp ? new Date(msg.timestamp * 1000).toLocaleTimeString() : null;
                    this.addMessage(msg.role || 'user', msg.content, timestamp);
                });
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
        
        const response = await fetch(endpoint, { ...options, headers });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(`HTTP error ${response.status}: ${JSON.stringify(errorData)}`);
        }
        return response.json();
    }
}

window.ChatComponent = ChatComponent;
